#!/usr/bin/env python3
"""Single-condition capture for ORDER-ARCH-01A-R1.

This script intentionally captures exactly one condition per invocation.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
CHANNELS = [f"c{i}_raw" for i in range(8)]
FIELDNAMES = ["phase", "condition", "session_id", "seq", "timestamp_us", *CHANNELS]
CONDITION_ORDER = ["100k", "47k", "22k", "10k", "10k_REPEAT", "22k_REPEAT", "47k_REPEAT", "100k_REPEAT"]
PIN2_MANUAL_CONDITIONS = {"47k", "22k", "10k"}


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "UNKNOWN"


def parse_float(text: str) -> Optional[float]:
    text = text.strip()
    if not text:
        return None
    text = text.replace("ohm", "").replace("Ω", "").replace("V", "").replace("v", "").replace(" ", "")
    multipliers = {"k": 1_000.0, "K": 1_000.0, "m": 1_000_000.0, "M": 1_000_000.0}
    if text[-1:] in multipliers:
        return float(text[:-1]) * multipliers[text[-1]]
    return float(text)


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
            raise RuntimeError(f"A01A session changed: expected {expected_session_id}, got {session_id}")
        return {
            "session_id": session_id,
            "seq": seq,
            "timestamp_us": timestamp_us,
            **{f"c{index}_raw": int(parts[index + raw_offset]) for index in range(8)},
        }
    except ValueError:
        return None


def collect_frames(
    serial_port,
    phase: str,
    condition: str,
    samples: int,
    timeout_seconds: float,
    expected_session_id: Optional[int],
) -> tuple[list[dict[str, int | str]], list[str]]:
    rows: list[dict[str, int | str]] = []
    gaps: list[str] = []
    previous_seq: Optional[int] = None
    started = time.monotonic()

    while len(rows) < samples and (time.monotonic() - started) < timeout_seconds:
        frame = read_a01a_frame(serial_port, expected_session_id)
        if frame is None:
            continue
        if previous_seq is not None and frame["seq"] != previous_seq + 1:
            gaps.append(f"{previous_seq}->{frame['seq']}")
        previous_seq = frame["seq"]
        rows.append({"phase": phase, "condition": condition, **frame})
        if len(rows) % 100 == 0:
            print(f"  {phase}: {len(rows)}/{samples}")

    return rows, gaps


def discard_frames(serial_port, seconds: float, expected_session_id: Optional[int]) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        read_a01a_frame(serial_port, expected_session_id)


def preview_col0_voltage(
    serial_port,
    label: str,
    vdda: float,
    expected_session_id: Optional[int],
    samples: int = 60,
) -> Optional[float]:
    rows, gaps = collect_frames(serial_port, f"PREVIEW_{label}", label, samples, max(5.0, samples / 20.0), expected_session_id)
    if not rows:
        print(f"Preview {label}: no valid A01A frames.")
        return None
    mean_raw = sum(float(row["c0_raw"]) for row in rows) / len(rows)
    mean_v = raw_to_voltage(mean_raw, vdda)
    print(f"Preview {label}: COL0 mean {mean_v:.6f} V from {len(rows)} samples, seq_gaps={len(gaps)}")
    return mean_v


def confirm_preview_window(
    serial_port,
    label: str,
    vdda: float,
    expected_v: float,
    tolerance_v: float,
    instruction: str,
    expected_session_id: Optional[int],
) -> bool:
    while True:
        input(instruction)
        mean_v = preview_col0_voltage(serial_port, label, vdda, expected_session_id)
        if mean_v is not None and abs(mean_v - expected_v) <= tolerance_v:
            return True
        print(f"Preview is outside expected window: target {expected_v:.6f} V +/- {tolerance_v:.3f} V.")
        choice = input("Fix the physical state and press ENTER to preview again, or type ABORT to stop: ")
        if choice.strip().upper() == "ABORT":
            return False


def write_rows(path: Path, rows: list[dict[str, int | str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def raw_to_voltage(raw: float, vdda: float) -> float:
    return raw * vdda / 65535.0


def phase_stats(rows: list[dict[str, int | str]], vdda: float) -> dict[str, float | int]:
    if not rows:
        return {"sample_count": 0}
    values = [float(row["c0_raw"]) for row in rows]
    mean_raw = sum(values) / len(values)
    variance = sum((value - mean_raw) ** 2 for value in values) / (len(values) - 1) if len(values) > 1 else 0.0
    std_raw = math.sqrt(variance)
    return {
        "sample_count": len(values),
        "mean_raw": mean_raw,
        "std_raw": std_raw,
        "mean_voltage": raw_to_voltage(mean_raw, vdda),
        "std_voltage": raw_to_voltage(std_raw, vdda),
        "min_raw": min(values),
        "max_raw": max(values),
    }


def upsert_result(dataset_dir: Path, result: dict[str, object]) -> None:
    path = dataset_dir / "condition_results.csv"
    rows: list[dict[str, object]] = []
    if path.exists():
        rows = list(csv.DictReader(path.open("r", encoding="utf-8-sig", newline="")))
        rows = [row for row in rows if row.get("condition") != result["condition"]]
    rows.append(result)
    rows.sort(key=lambda row: CONDITION_ORDER.index(str(row["condition"])) if str(row["condition"]) in CONDITION_ORDER else 999)

    fieldnames: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def create_or_load_metadata(dataset_dir: Path, args: argparse.Namespace) -> dict[str, object]:
    metadata_path = dataset_dir / "metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
    else:
        metadata = {
            "order": "ORDER-ARCH-01A-R1",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "git_commit": git_commit(),
            "firmware_mode": "ARCH_01A_DIRECT_TIA",
            "adc_resolution": "16bit",
            "adc_sampling_time": "64.5cycles",
            "dma_config": "DMA1_Stream1,DMA_REQUEST_ADC3,NORMAL,HALFWORD",
            "uart_baud": args.baud,
            "vdda_v": args.vdda,
            "vref_v": args.vref,
            "rf_ohm": args.rf_ohm,
            "open_reference_v": args.open_reference_v,
            "open_threshold_v": args.open_threshold_v,
            "open_samples": args.open_samples,
            "rtest_samples": args.rtest_samples,
            "discard_seconds": args.discard_seconds,
            "condition_order": CONDITION_ORDER,
            "dataset_dir": str(dataset_dir),
            "conditions": {},
        }
    metadata.setdefault("conditions", {})
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def acquire_current_session(serial_port, timeout_seconds: float = 5.0) -> int:
    started = time.monotonic()
    while time.monotonic() - started < timeout_seconds:
        frame = read_a01a_frame(serial_port)
        if frame is not None:
            return int(frame["session_id"])
    raise RuntimeError("No A01A frame observed while acquiring session.")


def save_metadata(dataset_dir: Path, metadata: dict[str, object]) -> None:
    metadata["updated_at"] = datetime.now().isoformat(timespec="seconds")
    (dataset_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def run_capture(args: argparse.Namespace) -> int:
    import serial

    if args.condition not in CONDITION_ORDER:
        print(f"Condition must be one of: {', '.join(CONDITION_ORDER)}")
        return 2
    if args.r_ohm <= 0:
        print("--r-ohm must be positive.")
        return 2

    if args.dataset_dir:
        dataset_dir = Path(args.dataset_dir).resolve()
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dataset_dir = ROOT / "data" / "arch_01a_r1" / f"{timestamp}_{args.run}"
    dataset_dir.mkdir(parents=True, exist_ok=True)

    if not args.overwrite and (dataset_dir / f"{args.condition}__RTEST_CAPTURE.csv").exists():
        print(f"Condition already exists: {args.condition}. Use --overwrite to replace it.")
        return 2

    metadata = create_or_load_metadata(dataset_dir, args)
    open_reference_v = float(metadata.get("open_reference_v", args.open_reference_v))
    open_threshold_v = float(metadata.get("open_threshold_v", args.open_threshold_v))
    vdda = float(metadata.get("vdda_v", args.vdda))
    vref = float(metadata.get("vref_v", args.vref))
    rf_ohm = float(metadata.get("rf_ohm", args.rf_ohm))

    print("ORDER-ARCH-01A-R1 single-condition capture")
    print(f"Dataset: {dataset_dir}")
    print(f"Condition: {args.condition}")
    print(f"Actual R: {args.r_ohm:g} ohm")
    print("Hardware: TEST_A fixed to U1 Pin2, TEST_B fixed to GND. Only one Rtest may bridge TEST_A and TEST_B.")

    condition_info = {
        "condition": args.condition,
        "actual_r_ohm": args.r_ohm,
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }

    with serial.Serial(args.port, args.baud, timeout=args.timeout) as serial_port:
        serial_port.reset_input_buffer()
        time.sleep(0.2)
        session_id = acquire_current_session(serial_port)
        print(f"Acquired A01A session_id={session_id}")
        metadata["active_session_id"] = session_id

        ok = confirm_preview_window(
            serial_port,
            "OPEN_CHECK_PRE",
            vdda,
            open_reference_v,
            open_threshold_v,
            "\nOPEN_CHECK_PRE: remove every resistor between TEST_A and TEST_B, then press ENTER for preview.",
            session_id,
        )
        if not ok:
            print("ABORTED before OPEN_CHECK_PRE capture.")
            return 2
        open_pre_rows, open_pre_gaps = collect_frames(
            serial_port,
            "OPEN_CHECK_PRE",
            args.condition,
            args.open_samples,
            max(10.0, args.open_samples / 50.0),
            session_id,
        )
        write_rows(dataset_dir / f"{args.condition}__OPEN_CHECK_PRE.csv", open_pre_rows)
        open_pre = phase_stats(open_pre_rows, vdda)
        open_pre_delta = float(open_pre["mean_voltage"]) - open_reference_v
        print(f"OPEN_PRE COL0 mean: {open_pre['mean_voltage']:.6f} V, delta vs reference: {open_pre_delta:+.6f} V")

        if len(open_pre_rows) != args.open_samples or open_pre_gaps:
            result = {
                **condition_info,
                "validity_flag": "INVALID_OPEN_PRE_SEQ",
                "invalid_reason": f"open_pre_samples={len(open_pre_rows)}, seq_gap_count={len(open_pre_gaps)}",
                "open_pre_mean_v": open_pre.get("mean_voltage", ""),
                "open_pre_std_v": open_pre.get("std_voltage", ""),
                "open_pre_seq_gap_count": len(open_pre_gaps),
            }
            upsert_result(dataset_dir, result)
            metadata["conditions"][args.condition] = result
            save_metadata(dataset_dir, metadata)
            return 1

        if abs(open_pre_delta) > open_threshold_v:
            result = {
                **condition_info,
                "validity_flag": "INVALID_OPEN_PRE_BASELINE",
                "invalid_reason": f"OPEN_PRE differs from reference by {open_pre_delta:+.6f} V",
                "open_pre_mean_v": open_pre["mean_voltage"],
                "open_pre_std_v": open_pre["std_voltage"],
                "open_pre_seq_gap_count": len(open_pre_gaps),
            }
            upsert_result(dataset_dir, result)
            metadata["conditions"][args.condition] = result
            save_metadata(dataset_dir, metadata)
            print("STOP: OPEN_CHECK_PRE is outside the 30 mV window.")
            return 1

        expected_vout = vref * (1.0 + rf_ohm / args.r_ohm)
        while True:
            input(f"\nRTEST_CAPTURE: INSERT ONLY {args.condition} BETWEEN TEST_A AND TEST_B, then press ENTER for preview.")
            print("Waiting 2.0 s for contact settling before preview...")
            time.sleep(2.0)
            preview_v = preview_col0_voltage(serial_port, f"RTEST_{args.condition}", vdda, session_id)
            if preview_v is not None and abs(preview_v - expected_vout) <= args.rtest_preview_tolerance_v:
                break
            print(f"Preview is not near expected RTEST output: expected {expected_vout:.6f} V +/- {args.rtest_preview_tolerance_v:.3f} V.")
            choice = input("Fix the resistor state and press ENTER to preview again, type CAPTURE to capture anyway, or ABORT to stop: ")
            choice = choice.strip().upper()
            if choice == "CAPTURE":
                break
            if choice == "ABORT":
                return 2

        print("Waiting 2.0 s for contact settling...")
        time.sleep(2.0)

        pin2_manual_v: Optional[float] = None
        base_condition = args.condition.replace("_REPEAT", "")
        if base_condition in PIN2_MANUAL_CONDITIONS and "_REPEAT" not in args.condition:
            while True:
                text = input(f"Measure U1 Pin2 during stable {args.condition} and enter V [Enter=skip]: ")
                try:
                    pin2_manual_v = parse_float(text)
                    break
                except ValueError:
                    print("Invalid voltage. Example: 1.03")

        print(f"Discarding {args.discard_seconds:.1f} s...")
        discard_frames(serial_port, args.discard_seconds, session_id)
        rtest_rows, rtest_gaps = collect_frames(
            serial_port,
            "RTEST_CAPTURE",
            args.condition,
            args.rtest_samples,
            max(30.0, args.rtest_samples / 50.0),
            session_id,
        )
        write_rows(dataset_dir / f"{args.condition}__RTEST_CAPTURE.csv", rtest_rows)
        rtest = phase_stats(rtest_rows, vdda)

        ok = confirm_preview_window(
            serial_port,
            "OPEN_CHECK_POST",
            vdda,
            float(open_pre["mean_voltage"]),
            open_threshold_v,
            f"\nOPEN_CHECK_POST: remove {args.condition}; TEST_A and TEST_B must be OPEN, then press ENTER for preview.",
            session_id,
        )
        if not ok:
            result = {
                **condition_info,
                "validity_flag": "INVALID_OPEN_POST_PREVIEW",
                "invalid_reason": "User aborted because OPEN_POST preview did not recover.",
                "open_pre_mean_v": open_pre["mean_voltage"],
                "open_pre_std_v": open_pre["std_voltage"],
                "rtest_mean_v": rtest.get("mean_voltage", ""),
                "rtest_std_v": rtest.get("std_voltage", ""),
            }
            upsert_result(dataset_dir, result)
            metadata["conditions"][args.condition] = result
            save_metadata(dataset_dir, metadata)
            return 1
        open_post_rows, open_post_gaps = collect_frames(
            serial_port,
            "OPEN_CHECK_POST",
            args.condition,
            args.open_samples,
            max(10.0, args.open_samples / 50.0),
            session_id,
        )
        write_rows(dataset_dir / f"{args.condition}__OPEN_CHECK_POST.csv", open_post_rows)
        open_post = phase_stats(open_post_rows, vdda)

    measured_vout = float(rtest.get("mean_voltage", math.nan))
    error_v = measured_vout - expected_vout
    error_percent = 100.0 * error_v / expected_vout if expected_vout else math.nan
    open_post_delta_vs_pre = float(open_post["mean_voltage"]) - float(open_pre["mean_voltage"])

    invalid_reasons = []
    if len(rtest_rows) != args.rtest_samples or rtest_gaps:
        invalid_reasons.append(f"RTEST seq/sample issue: samples={len(rtest_rows)}, gaps={len(rtest_gaps)}")
    if len(open_post_rows) != args.open_samples or open_post_gaps:
        invalid_reasons.append(f"OPEN_POST seq/sample issue: samples={len(open_post_rows)}, gaps={len(open_post_gaps)}")
    if abs(open_post_delta_vs_pre) > open_threshold_v:
        invalid_reasons.append(f"OPEN_POST differs from OPEN_PRE by {open_post_delta_vs_pre:+.6f} V")

    validity_flag = "VALID" if not invalid_reasons else "INVALID_CONTACT_STATE"

    result = {
        **condition_info,
        "completed_at": datetime.now().isoformat(timespec="seconds"),
        "validity_flag": validity_flag,
        "invalid_reason": "; ".join(invalid_reasons),
        "open_pre_mean_v": open_pre["mean_voltage"],
        "open_pre_std_v": open_pre["std_voltage"],
        "open_pre_seq_gap_count": len(open_pre_gaps),
        "rtest_mean_v": rtest["mean_voltage"],
        "rtest_std_v": rtest["std_voltage"],
        "rtest_seq_gap_count": len(rtest_gaps),
        "open_post_mean_v": open_post["mean_voltage"],
        "open_post_std_v": open_post["std_voltage"],
        "open_post_seq_gap_count": len(open_post_gaps),
        "open_post_delta_vs_pre_v": open_post_delta_vs_pre,
        "vexpected_v": expected_vout,
        "error_v": error_v,
        "error_percent": error_percent,
        "pin2_manual_v": "" if pin2_manual_v is None else pin2_manual_v,
    }

    upsert_result(dataset_dir, result)
    metadata["conditions"][args.condition] = result
    save_metadata(dataset_dir, metadata)

    print(f"\n{args.condition} {validity_flag}")
    print(f"OPEN_PRE:  {open_pre['mean_voltage']:.6f} V")
    print(f"RTEST:     {rtest['mean_voltage']:.6f} V, expected {expected_vout:.6f} V, error {error_v:+.6f} V")
    print(f"OPEN_POST: {open_post['mean_voltage']:.6f} V, delta vs pre {open_post_delta_vs_pre:+.6f} V")
    print(f"Result file: {dataset_dir / 'condition_results.csv'}")
    return 0 if validity_flag == "VALID" else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture one ORDER-ARCH-01A-R1 condition.")
    parser.add_argument("--condition", required=True, help=f"One of: {', '.join(CONDITION_ORDER)}")
    parser.add_argument("--r-ohm", required=True, type=float, help="Measured resistor value in ohms.")
    parser.add_argument("--dataset-dir", help="Shared R1 dataset directory. Omit only for first condition.")
    parser.add_argument("--run", default="run01")
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=0.2)
    parser.add_argument("--vdda", type=float, default=3.29)
    parser.add_argument("--vref", type=float, default=1.03)
    parser.add_argument("--rf-ohm", type=float, default=10170.0)
    parser.add_argument("--open-reference-v", type=float, default=1.035)
    parser.add_argument("--open-threshold-v", type=float, default=0.030)
    parser.add_argument("--open-samples", type=int, default=300)
    parser.add_argument("--rtest-samples", type=int, default=1000)
    parser.add_argument("--rtest-preview-tolerance-v", type=float, default=0.060)
    parser.add_argument("--discard-seconds", type=float, default=1.0)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run_capture(parse_args()))
