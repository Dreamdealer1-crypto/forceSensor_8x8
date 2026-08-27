#!/usr/bin/env python3
"""Capture ORDER-REBUILD-H2/H3 row-scan data.

H2 is implemented now. H3 entry points are intentionally left guarded because
the user will prepare the 2x2 resistor fixture later.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
COLS = [f"c{i}" for i in range(8)]


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "UNKNOWN"


def raw_to_mv(raw: int, vdda_v: float) -> float:
    return raw * vdda_v * 1000.0 / 65535.0


def parse_line(line: str, active_frame: Optional[dict]) -> tuple[Optional[dict], Optional[list[dict]], Optional[str]]:
    """Parse either native FRAME/Rn/END output or dedicated H2,ROWn output."""
    text = line.strip()
    if not text:
        return active_frame, None, None

    if text.startswith("FRAME,"):
        parts = text.split(",")
        if len(parts) >= 3:
            try:
                return {"seq": int(parts[1]), "timestamp_us": int(parts[2]), "rows": {}}, None, None
            except ValueError:
                return active_frame, None, f"bad FRAME line: {text}"

    if active_frame is not None and text.startswith("R") and "," in text:
        parts = text.split(",")
        try:
            row = int(parts[0][1:])
            values = [int(value) for value in parts[1:9]]
        except ValueError:
            return active_frame, None, f"bad row line: {text}"
        if 0 <= row < 8 and len(values) == 8:
            active_frame["rows"][row] = values
        return active_frame, None, None

    if active_frame is not None and text == "END":
        rows = active_frame.get("rows", {})
        if len(rows) != 8:
            return None, None, f"incomplete frame seq={active_frame.get('seq')} rows={sorted(rows.keys())}"
        parsed = []
        for row in range(8):
            values = rows[row]
            parsed.append(
                {
                    "frame": int(active_frame["seq"]),
                    "timestamp_us": int(active_frame["timestamp_us"]),
                    "row": row,
                    **{f"c{col}_raw": values[col] for col in range(8)},
                }
            )
        return None, parsed, None

    if text.startswith("H2,ROW"):
        parts = text.split(",")
        try:
            row = int(parts[1].replace("ROW", ""))
            values = [int(value) for value in parts[2:10]]
        except ValueError:
            return active_frame, None, f"bad H2 line: {text}"
        if 0 <= row < 8 and len(values) == 8:
            parsed = [
                {
                    "frame": -1,
                    "timestamp_us": int(time.time() * 1_000_000),
                    "row": row,
                    **{f"c{col}_raw": values[col] for col in range(8)},
                }
            ]
            return active_frame, parsed, None

    return active_frame, None, None


def write_csv(path: Path, rows: list[dict[str, object]], vdda_v: float) -> None:
    fields = []
    if any("experiment" in row for row in rows):
        fields.append("experiment")
    fields += ["frame", "timestamp_us", "row"]
    fields += [f"c{i}_raw" for i in range(8)]
    fields += [f"c{i}_mv" for i in range(8)]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            out = dict(row)
            for col in range(8):
                out[f"c{col}_mv"] = f"{raw_to_mv(int(row[f'c{col}_raw']), vdda_v):.3f}"
            writer.writerow(out)


def capture_h2(args: argparse.Namespace) -> int:
    import serial

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dataset_dir = Path(args.dataset_dir).resolve() if args.dataset_dir else ROOT / "data" / "rebuild_h2h3" / f"{timestamp}_{args.run}"
    dataset_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "order": "ORDER-REBUILD-H2H3",
        "phase": "H2",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "port": args.port,
        "baud": args.baud,
        "frames_requested": args.frames,
        "vdda_v": args.vdda,
        "pass_window_mv": [args.min_mv, args.max_mv],
        "hardware_required": "sensor disconnected; no test resistor between ROW and COL; 4051 controlled by row-scan firmware",
        "accepted_input_formats": ["FRAME/R0..R7/END", "H2,ROWn,c0..c7"],
    }
    (dataset_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print("ORDER-REBUILD-H2 row-scan capture")
    print("Hardware required: real sensor disconnected; no ROW-COL test resistors installed.")
    print(f"Output directory: {dataset_dir}")
    print(f"Opening {args.port} @ {args.baud} ...")

    rows: list[dict[str, object]] = []
    raw_log = dataset_dir / "h2_serial_raw.log"
    errors: list[str] = []
    active_frame: Optional[dict] = None
    complete_frames = 0
    started = time.monotonic()
    timeout = max(args.timeout, args.frames * 3.0)

    with serial.Serial(args.port, args.baud, timeout=0.5) as serial_port, raw_log.open("w", encoding="utf-8", newline="") as log:
        serial_port.reset_input_buffer()
        while complete_frames < args.frames and time.monotonic() - started < timeout:
            raw = serial_port.readline()
            if not raw:
                continue
            line = raw.decode("ascii", errors="ignore").strip()
            log.write(line + "\n")
            active_frame, parsed, error = parse_line(line, active_frame)
            if error:
                errors.append(error)
            if parsed:
                rows.extend(parsed)
                if len(parsed) == 8:
                    complete_frames += 1
                    print(f"  captured frame {complete_frames}/{args.frames}")
                elif len(rows) % 8 == 0:
                    complete_frames = len(rows) // 8
                    print(f"  captured H2 rows {len(rows)} ({complete_frames} row sets)")

    if not rows:
        raise RuntimeError("No H2 row data captured. Check firmware output format and COM port.")

    csv_path = dataset_dir / "h2_row_scan.csv"
    write_csv(csv_path, rows, args.vdda)
    if errors:
        (dataset_dir / "capture_warnings.txt").write_text("\n".join(errors) + "\n", encoding="utf-8")

    print(f"Saved {len(rows)} row records -> {csv_path}")
    print("Next: python tools/analyze_rebuild_h2h3.py --phase h2 " + str(dataset_dir))
    return 0


def capture_h3(args: argparse.Namespace) -> int:
    import serial

    if args.experiment not in {"a", "b", "c"}:
        raise SystemExit("H3 requires --experiment a, b, or c.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dataset_dir = Path(args.dataset_dir).resolve() if args.dataset_dir else ROOT / "data" / "rebuild_h2h3" / f"{timestamp}_{args.run}"
    dataset_dir.mkdir(parents=True, exist_ok=True)

    exp_name = f"h3_exp_{args.experiment}"
    metadata_path = dataset_dir / "metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
    else:
        metadata = {
            "order": "ORDER-REBUILD-H2H3",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "git_commit": git_commit(),
            "port": args.port,
            "baud": args.baud,
            "vdda_v": args.vdda,
            "h3_subarray": {"rows": [2, 3], "cols": [4, 5], "target_resistor_ohm": 47_000},
            "accepted_input_formats": ["FRAME/R0..R7/END"],
        }
    captures = metadata.setdefault("captures", {})
    captures[exp_name] = {
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "frames_requested": args.frames,
        "assumption": args.note or "manual fixture state supplied by user",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"ORDER-REBUILD-H3 experiment {args.experiment.upper()} capture")
    print("Subarray: ROW2/ROW3 x COL4/COL5. Reading existing ROW-scan firmware output.")
    print(f"Output directory: {dataset_dir}")
    print(f"Opening {args.port} @ {args.baud} ...")

    rows: list[dict[str, object]] = []
    raw_log = dataset_dir / f"{exp_name}_serial_raw.log"
    errors: list[str] = []
    active_frame: Optional[dict] = None
    complete_frames = 0
    started = time.monotonic()
    timeout = max(args.timeout, args.frames * 3.0)

    with serial.Serial(args.port, args.baud, timeout=0.5) as serial_port, raw_log.open("w", encoding="utf-8", newline="") as log:
        serial_port.reset_input_buffer()
        while complete_frames < args.frames and time.monotonic() - started < timeout:
            raw = serial_port.readline()
            if not raw:
                continue
            line = raw.decode("ascii", errors="ignore").strip()
            log.write(line + "\n")
            active_frame, parsed, error = parse_line(line, active_frame)
            if error:
                errors.append(error)
            if parsed and len(parsed) == 8:
                for parsed_row in parsed:
                    parsed_row["experiment"] = args.experiment.upper()
                rows.extend(parsed)
                complete_frames += 1
                if complete_frames % 10 == 0 or complete_frames == args.frames:
                    print(f"  captured frame {complete_frames}/{args.frames}")

    if not rows:
        raise RuntimeError("No H3 row data captured. Check firmware output and COM port.")

    csv_path = dataset_dir / f"{exp_name}.csv"
    write_csv(csv_path, rows, args.vdda)
    if errors:
        (dataset_dir / f"{exp_name}_capture_warnings.txt").write_text("\n".join(errors) + "\n", encoding="utf-8")

    print(f"Saved {len(rows)} row records -> {csv_path}")
    print("Next: python tools/analyze_rebuild_h2h3.py --phase h3 " + str(dataset_dir))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["h2", "h3"], default="h2")
    parser.add_argument("--experiment", choices=["a", "b", "c"], help="H3 experiment to capture")
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--frames", type=int, default=2, help="complete 8-row frames to capture for H2")
    parser.add_argument("--run", default="run01")
    parser.add_argument("--dataset-dir")
    parser.add_argument("--vdda", type=float, default=3.29)
    parser.add_argument("--min-mv", type=float, default=1020.0)
    parser.add_argument("--max-mv", type=float, default=1060.0)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--note", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.phase == "h3":
        return capture_h3(args)
    return capture_h2(args)


if __name__ == "__main__":
    raise SystemExit(main())
