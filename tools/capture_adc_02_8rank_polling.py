#!/usr/bin/env python3
"""Capture ORDER-ADC-02 ADC3 8-rank scan + polling + no-DMA evidence."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
RANKS = [f"r{i}" for i in range(1, 9)]
EXPECTED_CHANNELS = [9, 4, 8, 3, 6, 10, 11, 12]
EXPECTED_PINS = ["PF4", "PF5", "PF6", "PF7", "PF10", "PC0", "PC1", "PC2"]
EXPECTED_INDEX = [f"c{i}" for i in range(8)]
ADC01_REFERENCE_V = 1.143310


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "UNKNOWN"


def parse_adc02(line: str) -> Optional[dict[str, object]]:
    parts = line.strip().split(",")
    if len(parts) != 10 or parts[0] != "ADC02":
        return None
    try:
        row: dict[str, object] = {"frame_seq": int(parts[1])}
        for index, rank in enumerate(RANKS):
            row[rank] = int(parts[index + 2])
        return row
    except ValueError:
        return None


def parse_invalid(line: str) -> Optional[dict[str, int]]:
    parts = line.strip().split(",")
    if len(parts) != 3 or parts[0] != "ADC02_INVALID":
        return None
    try:
        return {"frame_seq": int(parts[1]), "invalid_count": int(parts[2])}
    except ValueError:
        return None


def parse_register(line: str) -> Optional[tuple[str, str]]:
    parts = line.strip().split(",")
    if len(parts) == 3 and parts[0] == "ADC02_REG":
        return parts[1], parts[2]
    return None


def parse_decode(line: str) -> Optional[dict[str, object]]:
    parts = line.strip().split(",")
    if not parts or parts[0] != "ADC02_DECODE":
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
        elif key == "DMA" and index + 1 < len(parts):
            out["dma"] = int(parts[index + 1])
            index += 2
        else:
            index += 1
    return out


def raw_to_voltage(raw: float, vdda: float) -> float:
    return raw * vdda / 65535.0


def write_frames(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["frame_seq", *RANKS])
        writer.writeheader()
        writer.writerows(rows)


def write_rank_stats(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "rank",
                "channel",
                "pin",
                "software_index",
                "mean_raw",
                "std_raw",
                "mean_voltage",
                "min_voltage",
                "max_voltage",
                "p2p_raw",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def make_manifest(dataset_dir: Path, summary: dict[str, object]) -> None:
    lines = [
        "# ORDER-ADC-02 8-Rank Polling Dataset",
        "",
        f"- Status: `{summary['status']}`",
        f"- Frames: `{summary['frame_count']}`",
        f"- Rank closest to 1.14 V: `r{summary['rank_closest_to_1p14']}`",
        f"- r3 mean voltage: `{summary['rank_stats'][2]['mean_voltage']:.6f} V`",
        "",
        "Files:",
        "",
        "- `raw_uart.log`",
        "- `frames.csv`",
        "- `rank_stats.csv`",
        "- `summary.json`",
    ]
    (dataset_dir / "MANIFEST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_supervisor_report(dataset_dir: Path, summary: dict[str, object]) -> Path:
    report_dir = ROOT / "reports" / "supervisor"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "2026-08-15_order-adc-02_8rank-polling-result.md"
    registers = summary["registers"]
    decode = summary["decode"]
    rank_stats = summary["rank_stats"]

    decode_lines = []
    for item, pin, software_index in zip(decode["ranks"], EXPECTED_PINS, EXPECTED_INDEX):
        decode_lines.append(f"- Rank{item['rank']} = Channel {item['channel']} -> {pin} -> {software_index}")
    stats_lines = []
    for row in rank_stats:
        stats_lines.append(
            f"| r{row['rank']} | {row['channel']} | {row['pin']} | {row['software_index']} | "
            f"{row['mean_raw']:.3f} | {row['std_raw']:.3f} | {row['mean_voltage']:.6f} V | "
            f"{row['min_voltage']:.6f} V | {row['max_voltage']:.6f} V | {row['p2p_raw']:.0f} |"
        )

    text = f"""# @监工 ORDER-ADC-02 8通道 Scan + Polling + 无DMA验证

状态：`{summary['status']}`

固定硬件：

- U2 Pin2 -> 100k -> GND
- U2 Pin1 -> PF6
- PF6 物理电压预期约 `1.14 V`
- 100k 未拆换
- 真实传感器未接回
- 4051 禁用

ADC 模式：

- `ADC3_8RANK_SCAN_POLLING_MODE`
- 8-rank scan / polling / no DMA
- 每帧 `HAL_ADC_Start()` 后逐 rank `HAL_ADC_PollForConversion()` + `HAL_ADC_GetValue()`，最后 `HAL_ADC_Stop()`

运行时寄存器：

| Register | Value |
|---|---:|
| SQR1 | `{registers.get('SQR1', '')}` |
| SQR2 | `{registers.get('SQR2', '')}` |
| SQR3 | `{registers.get('SQR3', '')}` |
| SQR4 | `{registers.get('SQR4', '')}` |
| PCSEL | `{registers.get('PCSEL', '')}` |
| DIFSEL | `{registers.get('DIFSEL', '')}` |
| CFGR | `{registers.get('CFGR', '')}` |
| CFGR2 | `{registers.get('CFGR2', '')}` |
| IER | `{registers.get('IER', '')}` |
| ISR | `{registers.get('ISR', '')}` |

运行时SQR解码：

{chr(10).join(decode_lines)}

PCSEL：

`{summary['pcsel_summary']}`

DIFSEL：

`{summary['difsel_summary']}`

1000帧统计：

| Rank | Channel | Pin | Index | mean_raw | std_raw | mean_voltage | min_voltage | max_voltage | p2p_raw |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(stats_lines)}

Rank closest to 1.14V：

`r{summary['rank_closest_to_1p14']}` = `{summary['closest_rank_voltage']:.6f} V`

r3 vs ADC-01：

- ADC-01 reference: `{ADC01_REFERENCE_V:.6f} V`
- ADC-02 r3/c2: `{rank_stats[2]['mean_voltage']:.6f} V`
- Difference: `{summary['r3_minus_adc01']:+.6f} V`

Frame integrity：

- timeouts / invalid_frames = `{summary['invalid_frames']}`
- frame_seq gaps = `{summary['seq_gap_count']}`
- rank anomalies = `{summary['rank_anomaly_count']}`

结论：

{summary['conclusion']}

证据：

- `{dataset_dir.relative_to(ROOT).as_posix()}/`
- `{(dataset_dir / 'MANIFEST.md').relative_to(ROOT).as_posix()}`
- `{(dataset_dir / 'raw_uart.log').relative_to(ROOT).as_posix()}`
- `{(dataset_dir / 'frames.csv').relative_to(ROOT).as_posix()}`
- `{(dataset_dir / 'rank_stats.csv').relative_to(ROOT).as_posix()}`
- `{(dataset_dir / 'summary.json').relative_to(ROOT).as_posix()}`
- `reports/logs/2026-08-15_order-adc-02_build.log`
- `reports/logs/2026-08-15_order-adc-02_flash.log`
- `reports/logs/2026-08-15_order-adc-02_capture.log`
"""
    report_path.write_text(text, encoding="utf-8")
    return report_path


def run(args: argparse.Namespace) -> int:
    import serial

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dataset_dir = ROOT / "data" / "adc_02" / f"{timestamp}_{args.run}"
    dataset_dir.mkdir(parents=True, exist_ok=False)
    raw_log_path = dataset_dir / "raw_uart.log"
    frames: list[dict[str, object]] = []
    registers: dict[str, str] = {}
    decode: dict[str, object] = {}
    invalid_frames = 0
    seq_gaps: list[str] = []
    last_seq: Optional[int] = None

    print("ORDER-ADC-02 8-rank polling capture")
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

            reg = parse_register(line)
            if reg is not None:
                registers[reg[0]] = reg[1]
                continue
            decoded = parse_decode(line)
            if decoded is not None:
                decode = decoded
                frames = []
                invalid_frames = 0
                seq_gaps = []
                last_seq = None
                print(f"  register decode observed: {decode}")
                continue
            invalid = parse_invalid(line)
            if invalid is not None and decode:
                invalid_frames += 1
                continue
            frame = parse_adc02(line)
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
        raise RuntimeError(f"Captured only {len(frames)} complete ADC02 frames before timeout.")

    write_frames(dataset_dir / "frames.csv", frames)
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
    write_rank_stats(dataset_dir / "rank_stats.csv", rank_stats)

    decoded_ranks = decode.get("ranks", [])
    decoded_channels = [int(row["channel"]) for row in decoded_ranks]
    pcsel_values = [int(row["pcsel"]) for row in decoded_ranks]
    difsel_values = [int(row["difsel"]) for row in decoded_ranks]
    sqr_ok = decoded_channels == EXPECTED_CHANNELS
    pcsel_ok = pcsel_values == [1] * 8
    difsel_ok = difsel_values == [0] * 8
    dma_ok = decode.get("dma") == 0
    mean_voltages = [float(row["mean_voltage"]) for row in rank_stats]
    closest_index = min(range(8), key=lambda idx: abs(mean_voltages[idx] - args.expected_pf6_voltage))
    r3_voltage = mean_voltages[2]
    r3_ok = abs(r3_voltage - ADC01_REFERENCE_V) <= args.adc01_match_tolerance
    closest_ok = closest_index == 2
    seq_ok = len(seq_gaps) == 0
    invalid_ok = invalid_frames == 0
    rank_anomalies = [
        f"r{row['rank']}_p2p_zero"
        for row in rank_stats
        if float(row["p2p_raw"]) == 0.0
    ]
    rank_anomaly_count = len(rank_anomalies)
    status = "PASS" if all([sqr_ok, pcsel_ok, difsel_ok, dma_ok, r3_ok, closest_ok, seq_ok, invalid_ok, rank_anomaly_count == 0]) else "FAIL"
    if status == "PASS":
        conclusion = (
            "8-rank ADC3 scan with CPU polling and no DMA is normal. PF6/ADC3_INP8 appears stably at rank3/c2, "
            "matching ADC-01. The remaining fault scope is DMA / buffer / cache / DMA read timing; wait for ADC-03."
        )
    else:
        conclusion = (
            "ADC-02 did not satisfy all pass criteria. Do not enter DMA/cache debugging; use the decoded SQR/PCSEL/DIFSEL, "
            "rank statistics, and frame integrity counters to classify the ADC-02 failure branch first."
        )

    summary: dict[str, object] = {
        "order": "ORDER-ADC-02",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "status": status,
        "frame_count": len(frames),
        "invalid_frames": invalid_frames,
        "seq_gap_count": len(seq_gaps),
        "seq_gaps": seq_gaps,
        "registers": registers,
        "decode": decode,
        "rank_stats": rank_stats,
        "sqr_ok": sqr_ok,
        "pcsel_ok": pcsel_ok,
        "difsel_ok": difsel_ok,
        "dma_ok": dma_ok,
        "rank_closest_to_1p14": closest_index + 1,
        "closest_rank_voltage": mean_voltages[closest_index],
        "r3_minus_adc01": r3_voltage - ADC01_REFERENCE_V,
        "r3_ok": r3_ok,
        "rank_anomaly_count": rank_anomaly_count,
        "rank_anomalies": rank_anomalies,
        "pcsel_summary": ", ".join(f"CH{ch}={pcsel}" for ch, pcsel in zip(EXPECTED_CHANNELS, pcsel_values)),
        "difsel_summary": ", ".join(f"CH{ch}={difsel}" for ch, difsel in zip(EXPECTED_CHANNELS, difsel_values)),
        "conclusion": conclusion,
    }
    (dataset_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    make_manifest(dataset_dir, summary)
    report_path = make_supervisor_report(dataset_dir, summary)

    print(f"STATUS: {status}")
    print(f"Rank closest to 1.14 V: r{closest_index + 1} = {mean_voltages[closest_index]:.6f} V")
    print(f"r3/c2 mean: {r3_voltage:.6f} V, diff vs ADC-01 {r3_voltage - ADC01_REFERENCE_V:+.6f} V")
    print(f"Report: {report_path}")
    return 0 if status == "PASS" else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture ORDER-ADC-02 ADC3 8-rank scan polling output.")
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--serial-timeout", type=float, default=0.2)
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    parser.add_argument("--run", default="run01")
    parser.add_argument("--frames", type=int, default=1000)
    parser.add_argument("--vdda", type=float, default=3.29)
    parser.add_argument("--expected-pf6-voltage", type=float, default=1.14)
    parser.add_argument("--adc01-match-tolerance", type=float, default=0.03)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
