#!/usr/bin/env python3
"""Capture ORDER-ADC-03A DMA baseline reproduction and audit evidence."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import subprocess
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
RANKS = [f"r{i}" for i in range(1, 9)]
EXPECTED_CHANNELS = [9, 4, 8, 3, 6, 10, 11, 12]
EXPECTED_PINS = ["PF4", "PF5", "PF6", "PF7", "PF10", "PC0", "PC1", "PC2"]
EXPECTED_INDEX = [f"c{i}" for i in range(8)]
ADC02_R3_REFERENCE_V = 1.143634


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "UNKNOWN"


def run_text(command: list[str]) -> str:
    try:
        return subprocess.check_output(command, cwd=ROOT, text=True, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as exc:
        return exc.output


def parse_reg(line: str) -> Optional[tuple[str, str]]:
    parts = line.strip().split(",")
    if len(parts) == 3 and parts[0] == "ADC03A_REG":
        return parts[1], parts[2]
    return None


def parse_mem(line: str) -> Optional[dict[str, object]]:
    parts = line.strip().split(",")
    if len(parts) != 7 or parts[0] != "ADC03A_MEM":
        return None
    return {"buffer_addr": parts[2], "buffer_size": int(parts[4]), "buffer_mod32": int(parts[6])}


def parse_decode(line: str) -> Optional[dict[str, object]]:
    parts = line.strip().split(",")
    if not parts or parts[0] != "ADC03A_DECODE":
        return None
    out: dict[str, object] = {"ranks": []}
    index = 1
    while index < len(parts):
        key = parts[index]
        if key.startswith("R") and index + 5 < len(parts):
            out["ranks"].append(
                {
                    "rank": int(key[1:]),
                    "channel": int(parts[index + 1]),
                    "pcsel": int(parts[index + 3]),
                    "difsel": int(parts[index + 5]),
                }
            )
            index += 6
        elif key in {"DMNGT", "DCACHE", "DMAMUX_REQ"} and index + 1 < len(parts):
            out[key.lower()] = int(parts[index + 1])
            index += 2
        else:
            index += 1
    return out


def parse_frame(line: str) -> Optional[dict[str, object]]:
    parts = line.strip().split(",")
    if len(parts) != 21 or parts[0] != "ADC03A":
        return None
    try:
        row: dict[str, object] = {"frame_seq": int(parts[1]), "timestamp_us": int(parts[2])}
        for index, rank in enumerate(RANKS):
            row[rank] = int(parts[index + 3])
        tail = parts[11:]
        for key, value in zip(
            [
                "ndtr_before_start",
                "ndtr_after_start",
                "ndtr_at_read",
                "tc_seen",
                "read_before_tc",
                "callback_seen",
                "adc_ovr",
                "dma_error_flags",
                "par_after_start",
                "m0ar_after_start",
            ],
            tail,
        ):
            row[key] = int(value, 0)
        return row
    except ValueError:
        return None


def raw_to_voltage(raw: float, vdda: float) -> float:
    return raw * vdda / 65535.0


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_static_audit(path: Path, mem: dict[str, object], decode: dict[str, object]) -> None:
    text = f"""# ORDER-ADC-03A Static DMA Audit

## DMA启动/读取时序

1. `HAL_ADC_Start_DMA()` 在 `Run_Adc03a_8Rank_Dma_Baseline_Audit_Mode()` 每帧调用。
2. CPU 在 `while (!adc_dma_done) {{}}` 返回后读取 `adc_dma_buffer[0..7]`。
3. 当前路径明确等待 `HAL_ADC_ConvCpltCallback()` 将 `adc_dma_done=true`。
4. 未发现“启动DMA后固定delay，然后直接读buffer”的路径。
5. 按当前03A路径，理论上不应在DMA尚未传完8项时读取buffer；逐帧 `read_before_tc` 用于实证。

## DMA生命周期

6. 每帧重新 `HAL_ADC_Start_DMA()`。
7. 每帧读取并输出后调用 `HAL_ADC_Stop_DMA()`。
8. 因等待 `adc_dma_done`，上一轮DMA完成前不会再次Start。
9. DMA NORMAL模式下 HAL 每轮Start应将 NDTR reload为8；逐帧记录 `ndtr_before_start` 和 `ndtr_at_read`。

## Buffer

10. 声明：`static uint16_t adc_dma_buffer[ADC_COL_COUNT];`
11. `sizeof(buffer)` = `{mem.get('buffer_size', '')}` bytes。
12. 运行时地址 = `{mem.get('buffer_addr', '')}`。
13. Linker使用 `STM32H743ZITx_FLASH_RAM_D1.ld`，RAM region为D1 AXI SRAM，起始 `0x24000000`。
14. 运行时地址 mod 32 = `{mem.get('buffer_mod32', '')}`。
15. buffer前后相邻变量需以本次 `firmware/cmake/resist_matrix_minimal.map` 为准，未手工重排或搬移buffer。

## Cache

16. `SCB->CCR` 的 D-cache bit由运行时dump确认。
17. 工程中未找到 `SCB_EnableDCache()` / `SCB_DisableDCache()` 调用。
18. 原代码未对ADC DMA buffer做 Clean/Invalidate。

## ADC/DMA管理

19. ADC3 CFGR DMNGT由运行时 `ADC_CFGR` / decode `dmngt` 确认。
20. DMA stream CR/FCR由运行时dump确认。
21. DMAMUX request由 `DMAMUX1_CHANNEL1_CCR` / decode `dmamux_req` 确认。
22. DMA peripheral address由 `DMA1_STREAM1_PAR` 确认，应指向ADC3 DR。
23. DMA memory address由 `DMA1_STREAM1_M0AR` 确认，应等于上述buffer地址。

Runtime decode snapshot:

```json
{json.dumps(decode, indent=2)}
```
"""
    path.write_text(text, encoding="utf-8")


def write_report(path: Path, dataset_dir: Path, summary: dict[str, object]) -> None:
    rank_rows = "\n".join(
        f"| r{row['rank']} | {row['mean_voltage']:.6f} V | {row['std_raw']:.3f} | {row['min_voltage']:.6f} V | {row['max_voltage']:.6f} V |"
        for row in summary["rank_stats"]
    )
    text = f"""# @监工 ORDER-ADC-03A DMA原始路径复现与审计

状态：`{summary['status']}`

DMA implementation:

- controller = `DMA1`
- stream/channel = `DMA1_Stream1 / DMAMUX1_Channel1`
- request = `DMA_REQUEST_ADC3` / runtime request `{summary['decode'].get('dmamux_req', '')}`
- mode = `DMA_NORMAL`
- PAlign = `HALFWORD`
- MAlign = `HALFWORD`

Buffer:

- address = `{summary['memory'].get('buffer_addr', '')}`
- size = `{summary['memory'].get('buffer_size', '')}`
- address_mod_32 = `{summary['memory'].get('buffer_mod32', '')}`
- memory_region = `D1 AXI SRAM / 0x24000000 region`

D-cache:

- enabled = `{summary['dcache_enabled']}`
- original cache maintenance = `NONE FOUND`

ADC DMNGT:

`{summary['decode'].get('dmngt', '')}` (`1` = DMA oneshot expected for HAL ADC DMA path)

Runtime DMA:

- PAR = `{summary['registers'].get('DMA1_STREAM1_PAR', '')}`
- M0AR = `{summary['registers'].get('DMA1_STREAM1_M0AR', '')}`
- PAR after Start_DMA = `{summary.get('par_after_start', '')}`
- M0AR after Start_DMA = `{summary.get('m0ar_after_start', '')}`
- NDTR initial = `{summary['registers'].get('DMA1_STREAM1_NDTR', '')}`
- NDTR after Start_DMA distribution = `{summary['ndtr_after_start_distribution']}`
- NDTR at read distribution = `{summary['ndtr_at_read_distribution']}`

Timing:

- waits_for_TC = `YES`
- read_before_tc_count = `{summary['read_before_tc_count']}`
- callback_count = `{summary['callback_seen_count']}`

1000-frame statistics:

| Rank | mean_voltage | std_raw | min_voltage | max_voltage |
|---|---:|---:|---:|---:|
{rank_rows}

r3 expected:

`~1.1436 V`

r3 DMA observed:

`{summary['rank_stats'][2]['mean_voltage']:.6f} V`

ADC OVR count = `{summary['adc_ovr_count']}`
DMA error count = `{summary['dma_error_count']}`

Most likely DMA-layer mechanism based on evidence:

{summary['mechanism']}

Evidence:

- `{dataset_dir.relative_to(ROOT).as_posix()}/`
- `{(dataset_dir / 'metadata.json').relative_to(ROOT).as_posix()}`
- `{(dataset_dir / 'runtime_register_dump.txt').relative_to(ROOT).as_posix()}`
- `{(dataset_dir / 'dma_static_audit.md').relative_to(ROOT).as_posix()}`
- `{(dataset_dir / 'frames.csv').relative_to(ROOT).as_posix()}`
- `{(dataset_dir / 'analysis_summary.json').relative_to(ROOT).as_posix()}`
- `{(dataset_dir / 'code_diff.patch').relative_to(ROOT).as_posix()}`
- `reports/logs/2026-08-15_order-adc-03a_build.log`
- `reports/logs/2026-08-15_order-adc-03a_flash.log`
- `reports/logs/2026-08-15_order-adc-03a_capture.log`
"""
    path.write_text(text, encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    import serial

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dataset_dir = ROOT / "data" / "adc_03a" / f"{timestamp}_{args.run}"
    dataset_dir.mkdir(parents=True, exist_ok=False)
    raw_log_path = dataset_dir / "raw_uart.log"
    runtime_dump_path = dataset_dir / "runtime_register_dump.txt"
    frames: list[dict[str, object]] = []
    registers: dict[str, str] = {}
    memory: dict[str, object] = {}
    decode: dict[str, object] = {}
    runtime_lines: list[str] = []
    last_seq: Optional[int] = None
    seq_gaps: list[str] = []

    print("ORDER-ADC-03A DMA baseline audit capture")
    print(f"Dataset: {dataset_dir}")
    deadline = time.monotonic() + args.timeout_seconds
    with serial.Serial(args.port, args.baud, timeout=args.serial_timeout) as serial_port, raw_log_path.open("w", encoding="utf-8") as raw_log:
        serial_port.reset_input_buffer()
        while len(frames) < args.frames and time.monotonic() < deadline:
            raw = serial_port.readline()
            if not raw:
                continue
            line = raw.decode("ascii", errors="ignore").strip()
            raw_log.write(line + "\n")
            raw_log.flush()
            if line.startswith("ADC03A_REG") or line.startswith("ADC03A_MEM") or line.startswith("ADC03A_DECODE"):
                runtime_lines.append(line)
            reg = parse_reg(line)
            if reg is not None:
                registers[reg[0]] = reg[1]
                continue
            mem = parse_mem(line)
            if mem is not None:
                memory = mem
                continue
            decoded = parse_decode(line)
            if decoded is not None:
                decode = decoded
                frames = []
                last_seq = None
                seq_gaps = []
                print(f"  runtime decode observed: {decode}")
                continue
            frame = parse_frame(line)
            if frame is None or not decode:
                continue
            seq = int(frame["frame_seq"])
            if last_seq is not None and seq != last_seq + 1:
                seq_gaps.append(f"{last_seq}->{seq}")
            last_seq = seq
            frames.append(frame)
            if len(frames) % 100 == 0:
                print(f"  frames: {len(frames)}/{args.frames}")

    if len(frames) < args.frames:
        raise RuntimeError(f"Captured only {len(frames)} ADC03A frames before timeout.")

    runtime_dump_path.write_text("\n".join(runtime_lines) + "\n", encoding="utf-8")
    fields = [
        "frame_seq",
        "timestamp_us",
        *RANKS,
        "ndtr_before_start",
        "ndtr_after_start",
        "ndtr_at_read",
        "tc_seen",
        "read_before_tc",
        "callback_seen",
        "adc_ovr",
        "dma_error_flags",
        "par_after_start",
        "m0ar_after_start",
    ]
    write_csv(dataset_dir / "frames.csv", frames, fields)
    rank_stats: list[dict[str, object]] = []
    for index, rank in enumerate(RANKS):
        raw_values = [float(row[rank]) for row in frames]
        voltages = [raw_to_voltage(value, args.vdda) for value in raw_values]
        rank_stats.append(
            {
                "rank": index + 1,
                "channel": EXPECTED_CHANNELS[index],
                "pin": EXPECTED_PINS[index],
                "software_index": EXPECTED_INDEX[index],
                "mean_raw": statistics.mean(raw_values),
                "std_raw": statistics.stdev(raw_values) if len(raw_values) > 1 else 0.0,
                "mean_voltage": statistics.mean(voltages),
                "min_voltage": min(voltages),
                "max_voltage": max(voltages),
                "p2p_raw": max(raw_values) - min(raw_values),
            }
        )

    r3 = float(rank_stats[2]["mean_voltage"])
    read_before_tc_count = sum(int(row["read_before_tc"]) for row in frames)
    callback_seen_count = sum(int(row["callback_seen"]) for row in frames)
    adc_ovr_count = sum(int(row["adc_ovr"]) for row in frames)
    dma_error_count = sum(1 for row in frames if int(row["dma_error_flags"]) != 0)
    ndtr_dist = dict(Counter(int(row["ndtr_at_read"]) for row in frames))
    reproduced = abs(r3 - args.baseline_voltage) <= args.reproduced_tolerance
    dma_error = adc_ovr_count > 0 or dma_error_count > 0
    if dma_error:
        status = "DMA_ERROR"
    elif reproduced:
        status = "REPRODUCED"
    else:
        status = "NOT_REPRODUCED"
    if status == "NOT_REPRODUCED":
        mechanism = (
            "This DMA baseline path waits for HAL_ADC_ConvCpltCallback before reading the buffer. "
            "In this run r3/c2 remains near the ADC-02 polling reference, so the original failure was not reproduced under this exact audited DMA timing."
        )
    elif status == "REPRODUCED":
        mechanism = (
            "DMA r3/c2 fell back near the baseline despite valid ADC-02 polling. Correlate frames against read_before_tc, NDTR, and DMA flags before choosing ADC-03B/C."
        )
    else:
        mechanism = "DMA/ADC error flags were observed; submit registers and frame counters before any repair."

    summary: dict[str, object] = {
        "order": "ORDER-ADC-03A",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "status": status,
        "frame_count": len(frames),
        "registers": registers,
        "memory": memory,
        "decode": decode,
        "dcache_enabled": "YES" if decode.get("dcache") else "NO",
        "rank_stats": rank_stats,
        "r3_dma_observed_v": r3,
        "r3_minus_adc02": r3 - ADC02_R3_REFERENCE_V,
        "read_before_tc_count": read_before_tc_count,
        "callback_seen_count": callback_seen_count,
        "tc_seen_count": sum(int(row["tc_seen"]) for row in frames),
        "adc_ovr_count": adc_ovr_count,
        "dma_error_count": dma_error_count,
        "ndtr_at_read_distribution": ndtr_dist,
        "ndtr_after_start_distribution": dict(Counter(int(row["ndtr_after_start"]) for row in frames)),
        "ndtr_before_start_distribution": dict(Counter(int(row["ndtr_before_start"]) for row in frames)),
        "par_after_start": f"0x{int(frames[0]['par_after_start']):08X}",
        "m0ar_after_start": f"0x{int(frames[0]['m0ar_after_start']):08X}",
        "seq_gap_count": len(seq_gaps),
        "seq_gaps": seq_gaps,
        "mechanism": mechanism,
    }
    (dataset_dir / "analysis_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    (dataset_dir / "metadata.json").write_text(
        json.dumps({"order": "ORDER-ADC-03A", "dataset_dir": str(dataset_dir), "git_commit": git_commit()}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    write_static_audit(dataset_dir / "dma_static_audit.md", memory, decode)
    (dataset_dir / "code_diff.patch").write_text(run_text(["git", "diff", "--", "firmware", "tools"]), encoding="utf-8")
    (dataset_dir / "MANIFEST.md").write_text(
        f"# ORDER-ADC-03A Dataset\n\n- Status: `{status}`\n- Frames: `{len(frames)}`\n- r3 DMA observed: `{r3:.6f} V`\n",
        encoding="utf-8",
    )
    report_path = ROOT / "reports" / "supervisor" / "2026-08-15_order-adc-03a_dma-baseline-audit-result.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_report(report_path, dataset_dir, summary)
    print(f"STATUS: {status}")
    print(f"r3 DMA observed: {r3:.6f} V, diff vs ADC-02 {r3 - ADC02_R3_REFERENCE_V:+.6f} V")
    print(f"read_before_tc_count={read_before_tc_count}, callback_seen_count={callback_seen_count}")
    print(f"Report: {report_path}")
    return 0 if status != "DMA_ERROR" else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture ORDER-ADC-03A DMA baseline audit output.")
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--serial-timeout", type=float, default=0.2)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--run", default="run01")
    parser.add_argument("--frames", type=int, default=1000)
    parser.add_argument("--vdda", type=float, default=3.29)
    parser.add_argument("--baseline-voltage", type=float, default=1.035)
    parser.add_argument("--reproduced-tolerance", type=float, default=0.03)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
