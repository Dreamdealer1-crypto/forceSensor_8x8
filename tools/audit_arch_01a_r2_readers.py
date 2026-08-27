#!/usr/bin/env python3
"""ORDER-ARCH-01A-R2 software acquisition-chain audit.

Runs three serial reader styles without asking the user to change hardware.
"""

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
READERS = ["raw_terminal_reader", "r1_preview_reader", "r1_capture_reader"]
CHANNELS = [f"c{i}_raw" for i in range(8)]


def process_check(port: str) -> list[dict[str, object]]:
    pattern = f"{port}|serial|A01A|capture_arch|live_pressure|r1|direct_tia|pyserial"
    script = (
        "$out = Get-CimInstance Win32_Process | "
        f"Where-Object {{ $_.Name -match 'python|powershell|putty|teraterm|mobaxterm' -and ($_.CommandLine -match '{pattern}') }} | "
        "Select-Object ProcessId,Name,CommandLine; "
        "$out | ConvertTo-Json -Depth 3"
    )
    try:
        text = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", script],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return []
    if not text:
        return []
    loaded = json.loads(text)
    if isinstance(loaded, dict):
        return [loaded]
    return list(loaded)


def parse_a01a_line(line: str) -> Optional[dict[str, int]]:
    line = line.strip()
    if not line.startswith("A01A,"):
        return None
    parts = line.split(",")
    try:
        if len(parts) == 12:
            session_id = int(parts[1])
            seq = int(parts[2])
            timestamp_us = int(parts[3])
            raw_offset = 4
        elif len(parts) == 11:
            session_id = 0
            seq = int(parts[1])
            timestamp_us = int(parts[2])
            raw_offset = 3
        else:
            return None
        return {
            "session_id": session_id,
            "seq": seq,
            "timestamp_us": timestamp_us,
            **{f"c{index}_raw": int(parts[index + raw_offset]) for index in range(8)},
        }
    except ValueError:
        return None


def read_line(serial_port) -> tuple[str, Optional[dict[str, int]]]:
    raw = serial_port.readline()
    if not raw:
        return "", None
    line = raw.decode("ascii", errors="ignore").strip()
    return line, parse_a01a_line(line)


def acquire_session(serial_port, raw_log, timeout_seconds: float = 5.0) -> int:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        line, frame = read_line(serial_port)
        if line:
            raw_log.write(line + "\n")
        if frame is not None:
            return int(frame["session_id"])
    raise RuntimeError("No A01A frame observed while acquiring session.")


def collect_reader(reader: str, args: argparse.Namespace, dataset_dir: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    import serial

    raw_path = dataset_dir / f"{reader}.log"
    csv_path = dataset_dir / f"{reader}.csv"
    frames: list[dict[str, int]] = []
    malformed_count = 0
    wrong_session_count = 0

    with serial.Serial(args.port, args.baud, timeout=args.timeout) as serial_port, raw_path.open("w", encoding="utf-8") as raw_log:
        serial_port.reset_input_buffer()
        time.sleep(args.open_settle_seconds)
        session_id = acquire_session(serial_port, raw_log)

        if reader == "r1_capture_reader":
            discard_until = time.monotonic() + args.capture_discard_seconds
            while time.monotonic() < discard_until:
                line, frame = read_line(serial_port)
                if line:
                    raw_log.write(line + "\n")
                if frame is None and line:
                    malformed_count += 1

        deadline = time.monotonic() + args.reader_timeout_seconds
        while len(frames) < args.samples and time.monotonic() < deadline:
            line, frame = read_line(serial_port)
            if line:
                raw_log.write(line + "\n")
            if not line:
                continue
            if frame is None:
                malformed_count += 1
                continue
            if frame["session_id"] != session_id:
                wrong_session_count += 1
                continue
            frames.append(frame)

    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["reader", "session_id", "seq", "timestamp_us", *CHANNELS])
        writer.writeheader()
        for frame in frames:
            writer.writerow({"reader": reader, **frame})

    seqs = [int(frame["seq"]) for frame in frames]
    c0 = [int(frame["c0_raw"]) for frame in frames]
    vdda = args.vdda
    gaps = []
    for previous, current in zip(seqs, seqs[1:]):
        if current != previous + 1:
            gaps.append(f"{previous}->{current}")

    stat = {
        "reader": reader,
        "session_id": frames[0]["session_id"] if frames else session_id,
        "frame_count": len(frames),
        "first_seq": seqs[0] if seqs else "",
        "last_seq": seqs[-1] if seqs else "",
        "dropped_frames": sum(max(0, int(gap.split("->")[1]) - int(gap.split("->")[0]) - 1) for gap in gaps),
        "seq_gap_count": len(gaps),
        "wrong_session_count": wrong_session_count,
        "malformed_count": malformed_count,
        "c0_mean_raw": statistics.mean(c0) if c0 else "",
        "c0_std_raw": statistics.stdev(c0) if len(c0) > 1 else 0,
        "c0_mean_v": statistics.mean(c0) * vdda / 65535.0 if c0 else "",
        "c0_std_v": statistics.stdev(c0) * vdda / 65535.0 if len(c0) > 1 else 0,
        "raw_log": str(raw_path),
        "csv": str(csv_path),
    }
    audit_rows = [
        {
            "reader": reader,
            "gap": gap,
        }
        for gap in gaps
    ]
    if not audit_rows:
        audit_rows.append({"reader": reader, "gap": ""})
    return stat, audit_rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run(args: argparse.Namespace) -> int:
    if args.dataset_dir:
        dataset_dir = Path(args.dataset_dir).resolve()
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dataset_dir = ROOT / "data" / "arch_01a_r2" / f"{timestamp}_{args.run}"
    dataset_dir.mkdir(parents=True, exist_ok=True)

    before = process_check(args.port)
    (dataset_dir / "process_check_before.json").write_text(json.dumps(before, indent=2), encoding="utf-8")

    stats_rows: list[dict[str, object]] = []
    audit_rows: list[dict[str, object]] = []
    for reader in READERS:
        print(f"Running {reader}...")
        stat, reader_audit = collect_reader(reader, args, dataset_dir)
        stats_rows.append(stat)
        audit_rows.extend(reader_audit)
        print(
            f"  {reader}: session={stat['session_id']} frames={stat['frame_count']} "
            f"c0={float(stat['c0_mean_v']):.6f} V gaps={stat['seq_gap_count']}"
        )
        time.sleep(args.between_readers_seconds)

    after = process_check(args.port)
    (dataset_dir / "process_check_after.json").write_text(json.dumps(after, indent=2), encoding="utf-8")
    write_csv(dataset_dir / "reader_stats.csv", stats_rows)
    write_csv(dataset_dir / "session_seq_audit.csv", audit_rows)

    means = [float(row["c0_mean_v"]) for row in stats_rows if row["c0_mean_v"] != ""]
    max_diff_v = max(means) - min(means) if means else float("nan")
    session_ids = {row["session_id"] for row in stats_rows}
    status = "PASS"
    reasons = []
    if max_diff_v >= args.max_reader_diff_v:
        status = "FAIL"
        reasons.append(f"reader c0 mean spread {max_diff_v:.6f} V >= {args.max_reader_diff_v:.6f} V")
    if len(session_ids) != 1:
        status = "FAIL"
        reasons.append(f"reader sessions differ: {sorted(session_ids)}")
    if any(int(row["seq_gap_count"]) != 0 for row in stats_rows):
        status = "FAIL"
        reasons.append("one or more readers had sequence gaps")
    if any(int(row["wrong_session_count"]) != 0 for row in stats_rows):
        status = "FAIL"
        reasons.append("one or more readers observed wrong-session frames")

    result = {
        "order": "ORDER-ARCH-01A-R2",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "reasons": reasons,
        "dataset_dir": str(dataset_dir),
        "vdda_v": args.vdda,
        "port": args.port,
        "samples_per_reader": args.samples,
        "max_reader_diff_v": max_diff_v,
        "reader_sessions": sorted(session_ids),
    }
    (dataset_dir / "audit_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"Dataset: {dataset_dir}")
    print(f"STATUS: {status}")
    if reasons:
        print("Reasons:")
        for reason in reasons:
            print(f"- {reason}")
    return 0 if status == "PASS" else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ORDER-ARCH-01A-R2 reader consistency audit.")
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=0.2)
    parser.add_argument("--samples", type=int, default=300)
    parser.add_argument("--vdda", type=float, default=3.29)
    parser.add_argument("--run", default="run01")
    parser.add_argument("--dataset-dir")
    parser.add_argument("--open-settle-seconds", type=float, default=0.2)
    parser.add_argument("--capture-discard-seconds", type=float, default=1.0)
    parser.add_argument("--reader-timeout-seconds", type=float, default=12.0)
    parser.add_argument("--between-readers-seconds", type=float, default=0.2)
    parser.add_argument("--max-reader-diff-v", type=float, default=0.005)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
