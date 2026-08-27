#!/usr/bin/env python3
"""ORDER-ARCH-01A-R3A U2A/COL2 cross-channel capture."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
TARGET_COL = 2
CHANNELS = [f"c{i}_raw" for i in range(8)]
FIELDNAMES = ["state", "kind", "session_id", "seq", "timestamp_us", *CHANNELS]
SEQUENCE = [
    ("OPEN_PRE", "OPEN", None),
    ("100k", "RTEST", 100_000.0),
    ("OPEN_1", "OPEN", None),
    ("47k", "RTEST", 47_000.0),
    ("OPEN_2", "OPEN", None),
    ("22k", "RTEST", 22_000.0),
    ("OPEN_3", "OPEN", None),
    ("10k", "RTEST", 10_000.0),
    ("OPEN_POST", "OPEN", None),
]
R_ARG_MAP = {
    "100k": "r100_ohm",
    "47k": "r47_ohm",
    "22k": "r22_ohm",
    "10k": "r10_ohm",
}


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "UNKNOWN"


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


def read_frame(serial_port, expected_session_id: Optional[int] = None) -> Optional[dict[str, int]]:
    raw = serial_port.readline()
    if not raw:
        return None
    frame = parse_a01a_line(raw.decode("ascii", errors="ignore"))
    if frame is not None and expected_session_id is not None and frame["session_id"] != expected_session_id:
        raise RuntimeError(f"A01A session changed: expected {expected_session_id}, got {frame['session_id']}")
    return frame


def acquire_session(serial_port, timeout_seconds: float = 5.0) -> int:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        frame = read_frame(serial_port)
        if frame is not None:
            return int(frame["session_id"])
    raise RuntimeError("No A01A frame observed while acquiring session.")


def collect_frames(serial_port, state: str, kind: str, samples: int, timeout_seconds: float, session_id: int) -> tuple[list[dict[str, int | str]], list[str]]:
    rows: list[dict[str, int | str]] = []
    gaps: list[str] = []
    previous_seq: Optional[int] = None
    started = time.monotonic()
    while len(rows) < samples and (time.monotonic() - started) < timeout_seconds:
        frame = read_frame(serial_port, session_id)
        if frame is None:
            continue
        if previous_seq is not None and frame["seq"] != previous_seq + 1:
            gaps.append(f"{previous_seq}->{frame['seq']}")
        previous_seq = frame["seq"]
        rows.append({"state": state, "kind": kind, **frame})
        if len(rows) % 100 == 0:
            print(f"  {state}: {len(rows)}/{samples}")
    return rows, gaps


def discard_frames(serial_port, seconds: float, session_id: int) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        read_frame(serial_port, session_id)


def raw_to_voltage(raw: float, vdda: float) -> float:
    return raw * vdda / 65535.0


def stats(rows: list[dict[str, int | str]], vdda: float, channel: int) -> dict[str, float | int]:
    values = [float(row[f"c{channel}_raw"]) for row in rows]
    mean_raw = statistics.mean(values)
    std_raw = statistics.stdev(values) if len(values) > 1 else 0.0
    return {
        "sample_count": len(values),
        "mean_raw": mean_raw,
        "std_raw": std_raw,
        "mean_v": raw_to_voltage(mean_raw, vdda),
        "std_v": raw_to_voltage(std_raw, vdda),
        "min_raw": min(values),
        "max_raw": max(values),
        "p2p_raw": max(values) - min(values),
    }


def write_rows(path: Path, rows: list[dict[str, int | str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


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


def preview_target(serial_port, label: str, vdda: float, session_id: int, samples: int = 60) -> float:
    rows, gaps = collect_frames(serial_port, label, "PREVIEW", samples, max(5.0, samples / 20.0), session_id)
    if not rows:
        raise RuntimeError(f"No frames during preview {label}")
    value = stats(rows, vdda, TARGET_COL)["mean_v"]
    print(f"Preview {label}: COL{TARGET_COL} mean {value:.6f} V from {len(rows)} samples, seq_gaps={len(gaps)}")
    return float(value)


def expected_v(vref: float, rf_ohm: float, r_ohm: Optional[float]) -> float:
    return vref if r_ohm is None else vref * (1.0 + rf_ohm / r_ohm)


def confirm_state(serial_port, state: str, kind: str, expected: float, tolerance: float, vdda: float, session_id: int, instruction: str) -> bool:
    while True:
        input(instruction)
        value = preview_target(serial_port, state, vdda, session_id)
        if abs(value - expected) <= tolerance:
            return True
        print(f"Preview outside expected window: target {expected:.6f} V +/- {tolerance:.3f} V.")
        choice = input("Fix state and press ENTER to preview again, type CAPTURE to continue anyway, or ABORT to stop: ")
        choice = choice.strip().upper()
        if choice == "CAPTURE":
            return True
        if choice == "ABORT":
            return False


def condition_r(args: argparse.Namespace, state: str, nominal: Optional[float]) -> Optional[float]:
    if nominal is None:
        return None
    return float(getattr(args, R_ARG_MAP[state]))


def make_plots(dataset_dir: Path, summary: list[dict[str, object]], comparison: list[dict[str, object]], args: argparse.Namespace) -> None:
    mpl.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9.5,
            "axes.titlesize": 11,
            "axes.labelsize": 9.5,
            "axes.linewidth": 0.8,
            "axes.edgecolor": "#30343b",
            "grid.color": "#d8dde6",
            "grid.linewidth": 0.6,
            "grid.alpha": 0.85,
            "legend.frameon": False,
            "svg.fonttype": "none",
        }
    )
    plots = dataset_dir / "plots"
    plots.mkdir(exist_ok=True)
    rtest = [row for row in summary if row["kind"] == "RTEST"]
    open_rows = [row for row in summary if row["kind"] == "OPEN"]
    blue = "#1f77b4"
    green = "#2f7d4f"
    red = "#b23b3b"
    gray = "#68707a"

    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    r = np.array([float(row["r_ohm"]) for row in rtest])
    y = np.array([float(row["mean_v"]) for row in rtest])
    theory = np.array([float(row["expected_v"]) for row in rtest])
    ax.plot(r, theory, color=gray, linewidth=1.5, linestyle="--", label="Expected")
    ax.plot(r, y, color=blue, marker="o", linewidth=1.6, label="U2 measured")
    ax.set_xscale("log")
    ax.invert_xaxis()
    for row in rtest:
        ax.annotate(str(row["state"]), (float(row["r_ohm"]), float(row["mean_v"])), xytext=(4, 5), textcoords="offset points", fontsize=8)
    ax.set_xlabel("Rtest (ohm, log scale)")
    ax.set_ylabel("COL2 Vout (V)")
    ax.set_title("U2A direct TIA response")
    ax.grid(True, which="both")
    ax.legend()
    fig.tight_layout()
    fig.savefig(plots / "01_r3a_u2_vout_vs_R.svg", format="svg", bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.8, 4.6))
    x = np.arange(len(summary))
    labels = [str(row["state"]) for row in summary]
    values = [float(row["mean_v"]) for row in summary]
    colors = [green if row["kind"] == "OPEN" else blue for row in summary]
    ax.bar(x, values, color=colors)
    ax.axhline(args.vref, color=gray, linestyle="--", linewidth=1.0, label="VREF")
    ax.set_xticks(x, labels, rotation=35, ha="right")
    ax.set_ylabel("COL2 Vout (V)")
    ax.set_title("R3A protocol states")
    ax.grid(True, axis="y")
    ax.legend()
    fig.tight_layout()
    fig.savefig(plots / "02_r3a_u2_state_sequence.svg", format="svg", bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    labels = [str(row["R"]) for row in comparison]
    u1 = [float(row["U1_Vout"]) if row["U1_Vout"] != "" else np.nan for row in comparison]
    u2 = [float(row["U2_Vout"]) if row["U2_Vout"] != "" else np.nan for row in comparison]
    theory_values = [float(row["Theory_Vout"]) if row["Theory_Vout"] != "" else np.nan for row in comparison]
    xpos = np.arange(len(labels))
    ax.plot(xpos, theory_values, color=gray, linestyle="--", marker="o", label="Theory")
    ax.plot(xpos, u1, color=red, marker="s", label="U1 prior")
    ax.plot(xpos, u2, color=blue, marker="o", label="U2 new")
    ax.set_xticks(xpos, labels)
    ax.set_ylabel("Vout (V)")
    ax.set_title("U1 vs U2 direct TIA comparison")
    ax.grid(True, axis="y")
    ax.legend()
    fig.tight_layout()
    fig.savefig(plots / "03_r3a_u1_u2_comparison.svg", format="svg", bbox_inches="tight")
    plt.close(fig)


def load_u1_prior() -> dict[str, float]:
    path = ROOT / "data" / "arch_01a_direct_tia" / "20260815_033955_run01" / "analysis_summary.csv"
    if not path.exists():
        return {}
    out: dict[str, float] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            condition = row["condition"]
            if condition == "OPEN_BASELINE_PRE":
                out["OPEN"] = float(row["mean_voltage"])
            elif condition in {"100k", "47k", "22k", "10k"}:
                out[condition] = float(row["mean_voltage"])
    return out


def run(args: argparse.Namespace) -> int:
    import serial

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dataset_dir = ROOT / "data" / "arch_01a_r3a" / f"{timestamp}_{args.run}"
    dataset_dir.mkdir(parents=True, exist_ok=False)
    metadata = {
        "order": "ORDER-ARCH-01A-R3A",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "firmware_mode": "ARCH_01A_DIRECT_TIA",
        "target": "U2A/COL2",
        "target_channel": "c2_raw",
        "vdda_v": args.vdda,
        "vref_v": args.vref,
        "rf_ohm": args.rf_ohm,
        "r_ohm": {"100k": args.r100_ohm, "47k": args.r47_ohm, "22k": args.r22_ohm, "10k": args.r10_ohm},
        "sequence": [state for state, _kind, _nominal in SEQUENCE],
    }

    summary: list[dict[str, object]] = []
    all_rows: list[dict[str, int | str]] = []
    print("ORDER-ARCH-01A-R3A U2A/COL2 capture")
    print(f"Dataset: {dataset_dir}")
    print("Hardware required: real sensor COL2 disconnected from U2 Pin2; TEST_U2_A=U2 Pin2; TEST_U2_B=GND.")

    with serial.Serial(args.port, args.baud, timeout=args.timeout) as serial_port:
        serial_port.reset_input_buffer()
        time.sleep(0.2)
        session_id = acquire_session(serial_port)
        metadata["session_id"] = session_id
        print(f"Acquired A01A session_id={session_id}")

        for state, kind, nominal in SEQUENCE:
            r_ohm = condition_r(args, state, nominal)
            expected = expected_v(args.vref, args.rf_ohm, r_ohm)
            tolerance = args.open_preview_tolerance_v if kind == "OPEN" else args.rtest_preview_tolerance_v
            samples = args.open_samples if kind == "OPEN" else args.rtest_samples
            instruction = (
                f"\n{state}: REMOVE resistor; TEST_U2_A and TEST_U2_B must be OPEN, then press ENTER for preview."
                if kind == "OPEN"
                else f"\n{state}: INSERT ONLY {state} BETWEEN TEST_U2_A and TEST_U2_B, then press ENTER for preview."
            )
            ok = confirm_state(serial_port, state, kind, expected, tolerance, args.vdda, session_id, instruction)
            if not ok:
                metadata["capture_status"] = f"ABORTED_AT_{state}"
                (dataset_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
                return 2
            if kind == "RTEST":
                print("Waiting 2.0 s for contact settling...")
                time.sleep(2.0)
                discard_frames(serial_port, args.discard_seconds, session_id)
            rows, gaps = collect_frames(serial_port, state, kind, samples, max(15.0, samples / 40.0), session_id)
            write_rows(dataset_dir / f"{state}.csv", rows)
            all_rows.extend(rows)
            item = stats(rows, args.vdda, TARGET_COL)
            summary.append(
                {
                    "state": state,
                    "kind": kind,
                    "target_col": "COL2",
                    "sample_count": item["sample_count"],
                    "mean_raw": item["mean_raw"],
                    "std_raw": item["std_raw"],
                    "mean_v": item["mean_v"],
                    "std_v": item["std_v"],
                    "r_ohm": "" if r_ohm is None else r_ohm,
                    "expected_v": expected,
                    "error_v": float(item["mean_v"]) - expected,
                    "seq_gap_count": len(gaps),
                }
            )
            print(f"{state}: COL2 mean {float(item['mean_v']):.6f} V, expected {expected:.6f} V, seq_gaps={len(gaps)}")

    write_rows(dataset_dir / "raw_all_states.csv", all_rows)
    write_csv(dataset_dir / "summary.csv", summary)
    u1_prior = load_u1_prior()
    u2_by_r = {row["state"]: float(row["mean_v"]) for row in summary if row["kind"] == "RTEST"}
    open_mean = float(np.mean([float(row["mean_v"]) for row in summary if row["kind"] == "OPEN"]))
    comparison = []
    for label, r_ohm in [("OPEN", None), ("100k", args.r100_ohm), ("47k", args.r47_ohm), ("22k", args.r22_ohm), ("10k", args.r10_ohm)]:
        comparison.append(
            {
                "R": label,
                "U1_Vout": u1_prior.get(label, ""),
                "U2_Vout": open_mean if label == "OPEN" else u2_by_r.get(label, ""),
                "Theory_Vout": args.vref if r_ohm is None else expected_v(args.vref, args.rf_ohm, r_ohm),
                "U2_minus_U1": "" if label not in u1_prior else ((open_mean if label == "OPEN" else u2_by_r.get(label, math.nan)) - u1_prior[label]),
            }
        )
    write_csv(dataset_dir / "u1_u2_comparison.csv", comparison)

    rtest_values = [float(row["mean_v"]) for row in summary if row["kind"] == "RTEST"]
    open_values = [float(row["mean_v"]) for row in summary if row["kind"] == "OPEN"]
    monotonic = all(rtest_values[i + 1] > rtest_values[i] for i in range(len(rtest_values) - 1))
    open_recovered = all(abs(value - args.vref) <= args.open_recovery_tolerance_v for value in open_values)
    status = "PASS" if monotonic and open_recovered and all(int(row["seq_gap_count"]) == 0 for row in summary) else "FAIL"
    result = {
        "status": status,
        "monotonic": monotonic,
        "open_recovered": open_recovered,
        "session_id": metadata.get("session_id"),
        "dataset_dir": str(dataset_dir),
    }
    (dataset_dir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    metadata["capture_status"] = f"{status}_CAPTURE_COMPLETE"
    (dataset_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    make_plots(dataset_dir, summary, comparison, args)

    print(f"\nDataset complete: {dataset_dir}")
    print(f"STATUS: {status}")
    print(f"Monotonic: {monotonic}")
    print(f"OPEN recovered: {open_recovered}")
    return 0 if status == "PASS" else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture ORDER-ARCH-01A-R3A U2/COL2 cross-channel sweep.")
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=0.2)
    parser.add_argument("--run", default="run01")
    parser.add_argument("--vdda", type=float, default=3.29)
    parser.add_argument("--vref", type=float, default=1.03)
    parser.add_argument("--rf-ohm", type=float, default=10170.0)
    parser.add_argument("--r100-ohm", type=float, default=97_710.0)
    parser.add_argument("--r47-ohm", type=float, default=45_960.0)
    parser.add_argument("--r22-ohm", type=float, default=22_320.0)
    parser.add_argument("--r10-ohm", type=float, default=9_920.0)
    parser.add_argument("--open-samples", type=int, default=300)
    parser.add_argument("--rtest-samples", type=int, default=1000)
    parser.add_argument("--discard-seconds", type=float, default=1.0)
    parser.add_argument("--open-preview-tolerance-v", type=float, default=0.050)
    parser.add_argument("--rtest-preview-tolerance-v", type=float, default=0.090)
    parser.add_argument("--open-recovery-tolerance-v", type=float, default=0.050)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
