#!/usr/bin/env python3
"""Interactive raw capture for ORDER-REBUILD-H1 transfer validation."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
CONDITIONS = [
    ("OPEN_BASELINE_PRE", None),
    ("1M", 1_000_000.0),
    ("680k", 680_000.0),
    ("470k", 470_000.0),
    ("220k", 220_000.0),
    ("100k", 100_000.0),
    ("68k", 68_000.0),
    ("47k", 47_000.0),
    ("22k", 22_000.0),
    ("10k", 10_000.0),
    ("100k_REPEAT", 100_000.0),
    ("47k_REPEAT", 47_000.0),
    ("22k_REPEAT", 22_000.0),
    ("10k_REPEAT", 10_000.0),
    ("OPEN_BASELINE_POST", None),
]
MEASURED_KEYS = [
    ("Rf_measured_ohm", "U1A Rf Pin1-Pin2 actual value, ohm", 9_970.0),
    ("Rf_U1B_measured_ohm", "U1B Rf Pin7-Pin6 actual value, ohm", 10_150.0),
    ("Rf_U2A_measured_ohm", "U2A Rf Pin1-Pin2 actual value, ohm", 10_090.0),
    ("Rf_U2B_measured_ohm", "U2B Rf Pin7-Pin6 actual value, ohm", 9_710.0),
    ("Rf_U3A_measured_ohm", "U3A Rf Pin1-Pin2 actual value, ohm", 10_000.0),
    ("Rf_U3B_measured_ohm", "U3B Rf Pin7-Pin6 actual value, ohm", 10_020.0),
    ("Rf_U4A_measured_ohm", "U4A Rf Pin1-Pin2 actual value, ohm", 9_970.0),
    ("Rf_U4B_measured_ohm", "U4B Rf Pin7-Pin6 actual value, ohm", 10_020.0),
    ("R10_measured_ohm", "10k resistor actual value, ohm", 10_120.0),
    ("R22_measured_ohm", "22k resistor actual value, ohm", 22_300.0),
    ("R47_measured_ohm", "47k resistor actual value, ohm", 45_900.0),
    ("R68_measured_ohm", "68k resistor actual value, ohm", 67_880.0),
    ("R100_measured_ohm", "100k resistor actual value, ohm", 98_280.0),
    ("R220_measured_ohm", "220k resistor actual value, ohm", 219_200.0),
    ("R470_measured_ohm", "470k resistor actual value, ohm", 475_000.0),
    ("R680_measured_ohm", "680k resistor actual value, ohm", 704_500.0),
    ("R1M_measured_ohm", "1M resistor actual value, ohm", 1_460_000.0),
    ("3V3_pre_v", "3V3 before sweep, V", 3.29),
    ("VREF_pre_v", "VREF before sweep, V", 1.03),
]
POST_KEYS = [
    ("3V3_post_v", "3V3 after sweep, V", 3.29),
    ("VREF_post_v", "VREF after sweep, V", 1.03),
]


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "UNKNOWN"


def parse_measurement(text: str) -> Optional[float]:
    text = text.strip()
    if not text or text.upper() == "MEASURED_R_UNAVAILABLE":
        return None
    text = text.replace("Ω", "").replace("ohm", "").replace(" ", "")
    multipliers = {"k": 1_000.0, "K": 1_000.0, "m": 1_000_000.0, "M": 1_000_000.0}
    if text[-1:] in multipliers:
        return float(text[:-1]) * multipliers[text[-1]]
    return float(text)


def prompt_measurements(items: list[tuple[str, str, Optional[float]]]) -> dict[str, object]:
    values: dict[str, object] = {}
    for key, label, nominal in items:
        suffix = " [Enter=unavailable]" if nominal is None else f" [Enter=use default {nominal:g}]"
        while True:
            text = input(f"{label}{suffix}: ")
            try:
                value = parse_measurement(text)
                values[key] = value if value is not None else nominal
                values[f"{key}_status"] = "MEASURED" if value is not None else "MEASURED_R_UNAVAILABLE"
                break
            except ValueError:
                print("Invalid number. Examples: 9980, 9.98k, 1.502M, or Enter.")
    return values


def read_a01a_frame(serial_port, expected_session_id: Optional[int] = None) -> Optional[dict[str, int]]:
    raw = serial_port.readline()
    if not raw:
        return None
    line = raw.decode("ascii", errors="ignore").strip()
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
        if expected_session_id is not None and session_id != expected_session_id:
            # Serial reads can begin in the middle of a line after a resume or
            # USB hiccup. Treat wrong-session frames as stale/garbled data and
            # keep waiting for the current session instead of aborting the run.
            return None
        return {
            "session_id": session_id,
            "seq": seq,
            "timestamp_us": timestamp_us,
            **{f"c{index}_raw": int(parts[index + raw_offset]) for index in range(8)},
        }
    except ValueError:
        return None


def acquire_current_session(serial_port, timeout_seconds: float = 5.0) -> int:
    started = time.monotonic()
    while time.monotonic() - started < timeout_seconds:
        frame = read_a01a_frame(serial_port)
        if frame is not None:
            return int(frame["session_id"])
    raise RuntimeError("No A01A frame observed while acquiring session.")


def collect_condition(
    serial_port,
    condition: str,
    samples: int,
    discard_seconds: float,
    expected_session_id: int,
) -> tuple[list[dict[str, int]], list[str]]:
    print(f"Discarding {discard_seconds:.1f} s for {condition}...")
    end_discard = time.monotonic() + discard_seconds
    while time.monotonic() < end_discard:
        read_a01a_frame(serial_port, expected_session_id)

    rows: list[dict[str, int]] = []
    gaps: list[str] = []
    previous_seq: Optional[int] = None
    started = time.monotonic()
    timeout = max(30.0, samples / 50.0)

    while len(rows) < samples and (time.monotonic() - started) < timeout:
        frame = read_a01a_frame(serial_port, expected_session_id)
        if frame is None:
            continue
        if previous_seq is not None and frame["seq"] != previous_seq + 1:
            gaps.append(f"{previous_seq}->{frame['seq']}")
        previous_seq = frame["seq"]
        rows.append({"condition": condition, **frame})
        if len(rows) % 100 == 0:
            print(f"  {condition}: {len(rows)}/{samples}")

    return rows, gaps


def write_condition_csv(path: Path, rows: list[dict[str, int]]) -> None:
    fieldnames = ["condition", "session_id", "seq", "timestamp_us"] + [f"c{i}_raw" for i in range(8)]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_condition_csv(path: Path) -> list[dict[str, int]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = []
        for row in csv.DictReader(file):
            rows.append(
                {
                    "condition": row["condition"],
                    "session_id": int(row.get("session_id", 0)),
                    "seq": int(row["seq"]),
                    "timestamp_us": int(row["timestamp_us"]),
                    **{f"c{index}_raw": int(row[f"c{index}_raw"]) for index in range(8)},
                }
            )
        return rows


def run_capture(args: argparse.Namespace) -> int:
    import serial

    if args.dataset_dir:
        dataset_dir = Path(args.dataset_dir).resolve()
        dataset_dir.mkdir(parents=True, exist_ok=True)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dataset_dir = ROOT / "data" / "rebuild_h1" / f"{timestamp}_{args.run}"
        dataset_dir.mkdir(parents=True, exist_ok=False)

    print("ORDER-REBUILD-H1 transfer capture")
    print("Hardware required: real sensor disconnected, 4051 disabled, Rtest only between TEST_A(U1 Pin2) and TEST_B(GND).")
    print("Measured values default to the 2026-08-18 user-reported values. Press Enter to accept each default.")
    metadata_path = dataset_dir / "metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
        measurements = dict(metadata.get("measurements", {}))
        print(f"Loaded metadata: {metadata_path}")
    else:
        measurements = prompt_measurements(MEASURED_KEYS)
        metadata: dict[str, object] = {
            "order": "ORDER-REBUILD-H1",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "git_commit": git_commit(),
            "firmware_mode": "A01A_RAW8_REUSED_FOR_REBUILD_H1",
            "adc_resolution": "16bit",
            "adc_sampling_time": "64.5cycles",
            "dma_config": "DMA1_Stream1,DMA_REQUEST_ADC3,NORMAL,HALFWORD",
            "uart_baud": args.baud,
            "sample_rate_target_hz": 100,
            "sample_target_per_condition": args.samples,
            "discard_seconds_per_condition": args.discard_seconds,
            "nominal_r_ohm": {condition: nominal for condition, nominal in CONDITIONS if nominal is not None},
            "measurements": measurements,
            "conditions": [condition for condition, _ in CONDITIONS],
            "dataset_dir": str(dataset_dir),
        }
        metadata["capture_status"] = "IN_PROGRESS"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    all_rows: list[dict[str, int]] = []
    failures: dict[str, object] = {}
    start_index = 0
    if args.start_at:
        condition_names = [condition for condition, _ in CONDITIONS]
        if args.start_at not in condition_names:
            print(f"Unknown --start-at condition: {args.start_at}")
            return 2
        start_index = condition_names.index(args.start_at)
        for condition, _nominal in CONDITIONS[:start_index]:
            condition_path = dataset_dir / f"{condition}.csv"
            if condition_path.exists():
                all_rows.extend(load_condition_csv(condition_path))
                print(f"Loaded previous {condition}: {condition_path}")
            else:
                print(f"Missing previous condition CSV for resume: {condition_path}")
                return 2

    with serial.Serial(args.port, args.baud, timeout=args.timeout) as serial_port:
        serial_port.reset_input_buffer()
        time.sleep(0.2)
        session_id = acquire_current_session(serial_port)
        print(f"Acquired A01A session_id={session_id}")
        metadata["active_session_id"] = session_id
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        for condition, _nominal in CONDITIONS[start_index:]:
            while True:
                input(f"\nConnect {condition} between TEST_A and TEST_B, confirm resistance in-circuit, then press ENTER.")
                rows, gaps = collect_condition(serial_port, condition, args.samples, args.discard_seconds, session_id)
                failed = len(rows) != args.samples or bool(gaps)
                if failed:
                    failures[condition] = {
                        "sample_count": len(rows),
                        "seq_gaps": gaps[:20],
                        "seq_gap_count": len(gaps),
                    }
                    print(f"FAIL for {condition}: samples={len(rows)}, seq_gap_count={len(gaps)}")
                    retry = input("Recapture this condition now? Type YES to retry, anything else to abort: ")
                    if retry.strip().upper() == "YES":
                        continue
                    metadata["capture_status"] = "ABORTED_WITH_FAILURE"
                    metadata["failures"] = failures
                    (dataset_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
                    return 2

                condition_path = dataset_dir / f"{condition}.csv"
                write_condition_csv(condition_path, rows)
                all_rows.extend(rows)
                write_condition_csv(dataset_dir / "raw_all_conditions.csv", all_rows)
                metadata["capture_status"] = "IN_PROGRESS"
                metadata["last_completed_condition"] = condition
                metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
                print(f"PASS {condition}: saved {len(rows)} samples -> {condition_path}")
                break

    print("\nSweep complete. Enter post measurements.")
    measurements.update(prompt_measurements(POST_KEYS))
    metadata["measurements"] = measurements
    metadata["capture_status"] = "PASS_CAPTURE_COMPLETE"
    metadata["completed_at"] = datetime.now().isoformat(timespec="seconds")

    write_condition_csv(dataset_dir / "raw_all_conditions.csv", all_rows)
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"\nDataset complete: {dataset_dir}")
    print(f"Metadata: {dataset_dir / 'metadata.json'}")
    print(f"Raw all: {dataset_dir / 'raw_all_conditions.csv'}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture ORDER-REBUILD-H1 transfer raw data.")
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=0.2)
    parser.add_argument("--samples", type=int, default=1000)
    parser.add_argument("--discard-seconds", type=float, default=1.0)
    parser.add_argument("--run", default="run01")
    parser.add_argument("--dataset-dir", help="Resume or write to an existing dataset directory.")
    parser.add_argument("--start-at", help="Resume capture from this condition name.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run_capture(parse_args()))
