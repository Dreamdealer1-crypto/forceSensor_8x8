#!/usr/bin/env python3
"""Capture ORDER-ADC-01 PF6/ADC3_INP8 single-channel polling evidence."""

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


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "UNKNOWN"


def parse_adc01(line: str) -> Optional[dict[str, object]]:
    parts = line.strip().split(",")
    if len(parts) != 4 or parts[0] != "ADC01":
        return None
    try:
        return {"seq": int(parts[1]), "raw": int(parts[2]), "voltage": float(parts[3])}
    except ValueError:
        return None


def parse_register(line: str) -> Optional[tuple[str, str]]:
    parts = line.strip().split(",")
    if len(parts) == 3 and parts[0] == "ADC01_REG":
        return parts[1], parts[2]
    return None


def parse_decode(line: str) -> Optional[dict[str, object]]:
    parts = line.strip().split(",")
    if len(parts) != 9 or parts[0] != "ADC01_DECODE":
        return None
    out: dict[str, object] = {}
    for index in range(1, len(parts), 2):
        key = parts[index]
        value = parts[index + 1]
        try:
            out[key] = int(value)
        except ValueError:
            out[key] = value
    return out


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["seq", "raw", "voltage"])
        writer.writeheader()
        writer.writerows(rows)


def make_manifest(dataset_dir: Path, summary: dict[str, object]) -> None:
    lines = [
        "# ORDER-ADC-01 PF6 Polling Dataset",
        "",
        f"- Status: `{summary['status']}`",
        f"- Samples: `{summary['count']}`",
        f"- Mean voltage: `{summary['mean_voltage']:.6f} V`",
        f"- Register decode: Rank1=`{summary['decode'].get('RANK1', '')}`, "
        f"PCSEL_CH8=`{summary['decode'].get('PCSEL_CH8', '')}`, "
        f"DIFSEL_CH8=`{summary['decode'].get('DIFSEL_CH8', '')}`, "
        f"DMA=`{summary['decode'].get('DMA', '')}`",
        "",
        "Files:",
        "",
        "- `raw_uart.log`",
        "- `samples.csv`",
        "- `summary.json`",
    ]
    (dataset_dir / "MANIFEST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_supervisor_report(dataset_dir: Path, summary: dict[str, object], args: argparse.Namespace) -> Path:
    report_dir = ROOT / "reports" / "supervisor"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "2026-08-15_order-adc-01_pf6-polling-result.md"
    decode = summary["decode"]
    registers = summary["registers"]
    text = f"""# @监工 ORDER-ADC-01 PF6 / ADC3_INP8 单通道 Polling 验证

状态：`{summary['status']}`

固定硬件状态：

- U2 Pin2 -> 100k -> GND
- U2 Pin1 -> PF6
- PF6 物理电压：用户/订单给定约 `{args.expected_voltage:.2f} V`
- 真实传感器未接回
- 4051 禁用

ADC 模式：

- `ADC3_PF6_SINGLE_POLLING_MODE`
- Single channel / polling / no DMA
- Channel: `ADC_CHANNEL_8 / ADC3_INP8`
- Rank: `1`
- 每点 `HAL_ADC_Start()` -> `HAL_ADC_PollForConversion()` -> `HAL_ADC_GetValue()` -> `HAL_ADC_Stop()`

运行时寄存器：

| Register | Value |
|---|---:|
| SQR1 | `{registers.get('SQR1', '')}` |
| SQR2 | `{registers.get('SQR2', '')}` |
| PCSEL | `{registers.get('PCSEL', '')}` |
| DIFSEL | `{registers.get('DIFSEL', '')}` |
| CFGR | `{registers.get('CFGR', '')}` |
| CFGR2 | `{registers.get('CFGR2', '')}` |

解码：

- Rank1 = `{decode.get('RANK1', '')}`
- PCSEL_CH8 = `{decode.get('PCSEL_CH8', '')}`
- DIFSEL_CH8 = `{decode.get('DIFSEL_CH8', '')}`
- DMA = `{decode.get('DMA', '')}`

样本统计：

| Field | Value |
|---|---:|
| count | `{summary['count']}` |
| mean_raw | `{summary['mean_raw']:.3f}` |
| std_raw | `{summary['std_raw']:.3f}` |
| mean_voltage | `{summary['mean_voltage']:.6f} V` |
| std_voltage | `{summary['std_voltage']:.6f} V` |
| min_voltage | `{summary['min_voltage']:.6f} V` |
| max_voltage | `{summary['max_voltage']:.6f} V` |
| seq_gap_count | `{summary['seq_gap_count']}` |
| rail_anomaly_count | `{summary['rail_anomaly_count']}` |

结论：

{summary['conclusion']}

证据：

- `{dataset_dir.relative_to(ROOT).as_posix()}/`
- `{(dataset_dir / 'MANIFEST.md').relative_to(ROOT).as_posix()}`
- `{(dataset_dir / 'raw_uart.log').relative_to(ROOT).as_posix()}`
- `{(dataset_dir / 'samples.csv').relative_to(ROOT).as_posix()}`
- `{(dataset_dir / 'summary.json').relative_to(ROOT).as_posix()}`
"""
    report_path.write_text(text, encoding="utf-8")
    return report_path


def run(args: argparse.Namespace) -> int:
    import serial

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dataset_dir = ROOT / "data" / "adc_01" / f"{timestamp}_{args.run}"
    dataset_dir.mkdir(parents=True, exist_ok=False)
    raw_log_path = dataset_dir / "raw_uart.log"
    samples: list[dict[str, object]] = []
    registers: dict[str, str] = {}
    decode: dict[str, object] = {}
    seq_gaps: list[str] = []
    last_seq: Optional[int] = None

    print("ORDER-ADC-01 PF6 polling capture")
    print(f"Dataset: {dataset_dir}")

    deadline = time.monotonic() + args.timeout_seconds
    with serial.Serial(args.port, args.baud, timeout=args.serial_timeout) as serial_port, raw_log_path.open("w", encoding="utf-8") as raw_log:
        serial_port.reset_input_buffer()
        while len(samples) < args.samples and time.monotonic() < deadline:
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
                samples = []
                seq_gaps = []
                last_seq = None
                print(f"  register decode observed: {decode}")
                continue
            sample = parse_adc01(line)
            if sample is None:
                continue
            if not decode:
                continue
            seq = int(sample["seq"])
            if last_seq is not None and seq != last_seq + 1:
                seq_gaps.append(f"{last_seq}->{seq}")
            last_seq = seq
            samples.append(sample)
            if len(samples) % 100 == 0:
                print(f"  samples: {len(samples)}/{args.samples}")

    if len(samples) < args.samples:
        raise RuntimeError(f"Captured only {len(samples)} ADC01 samples before timeout.")

    write_csv(dataset_dir / "samples.csv", samples)
    raw_values = [float(row["raw"]) for row in samples]
    voltages = [float(row["voltage"]) for row in samples]
    rail_anomalies = sum(1 for value in raw_values if value <= args.rail_low_raw or value >= args.rail_high_raw)
    config_ok = (
        decode.get("RANK1") == 8
        and decode.get("PCSEL_CH8") == 1
        and decode.get("DIFSEL_CH8") == 0
        and decode.get("DMA") == 0
    )
    mean_voltage = statistics.mean(voltages)
    voltage_ok = abs(mean_voltage - args.expected_voltage) <= args.expected_tolerance
    baseline_separated = mean_voltage >= args.baseline_voltage + args.baseline_margin
    rail_ok = rail_anomalies <= args.max_rail_anomalies
    seq_ok = len(seq_gaps) == 0
    status = "PASS" if config_ok and voltage_ok and baseline_separated and rail_ok and seq_ok else "FAIL"
    if status == "PASS":
        conclusion = (
            "PF6 GPIO/ADC3_INP8/ADC3 DR polling path can read the fixed ~1.14 V physical node. "
            "The problem should move upward to multi-channel scan / DMA / buffer / cache / read timing, but ADC-02 is required before changing DMA."
        )
    else:
        conclusion = (
            "PF6 single-channel polling did not satisfy ORDER-ADC-01 pass criteria. "
            "Do not enter DMA debugging; inspect PF6 analog setup, ADC3 channel 8 selection, PCSEL, DIFSEL, and runtime ADC3 configuration first."
        )

    summary: dict[str, object] = {
        "order": "ORDER-ADC-01",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "status": status,
        "port": args.port,
        "baud": args.baud,
        "count": len(samples),
        "mean_raw": statistics.mean(raw_values),
        "std_raw": statistics.stdev(raw_values) if len(raw_values) > 1 else 0.0,
        "min_raw": min(raw_values),
        "max_raw": max(raw_values),
        "mean_voltage": mean_voltage,
        "std_voltage": statistics.stdev(voltages) if len(voltages) > 1 else 0.0,
        "min_voltage": min(voltages),
        "max_voltage": max(voltages),
        "seq_gap_count": len(seq_gaps),
        "seq_gaps": seq_gaps,
        "rail_anomaly_count": rail_anomalies,
        "registers": registers,
        "decode": decode,
        "config_ok": config_ok,
        "voltage_ok": voltage_ok,
        "baseline_separated": baseline_separated,
        "rail_ok": rail_ok,
        "seq_ok": seq_ok,
        "conclusion": conclusion,
    }
    (dataset_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    make_manifest(dataset_dir, summary)
    report_path = make_supervisor_report(dataset_dir, summary, args)

    print(f"STATUS: {status}")
    print(f"Mean voltage: {mean_voltage:.6f} V")
    print(f"Decode: {decode}")
    print(f"Report: {report_path}")
    return 0 if status == "PASS" else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture ORDER-ADC-01 PF6 single-channel polling output.")
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--serial-timeout", type=float, default=0.2)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--run", default="run01")
    parser.add_argument("--samples", type=int, default=1000)
    parser.add_argument("--expected-voltage", type=float, default=1.14)
    parser.add_argument("--expected-tolerance", type=float, default=0.12)
    parser.add_argument("--baseline-voltage", type=float, default=1.03)
    parser.add_argument("--baseline-margin", type=float, default=0.06)
    parser.add_argument("--rail-low-raw", type=int, default=10)
    parser.add_argument("--rail-high-raw", type=int, default=65525)
    parser.add_argument("--max-rail-anomalies", type=int, default=0)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
