#!/usr/bin/env python3
"""Capture real 8x8 fabric sensor scans for ORDER-REBUILD-H4."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def apply_display_map(matrix: np.ndarray, row_origin: str, col_origin: str, transpose: bool) -> np.ndarray:
    mapped = np.array(matrix, copy=True)
    if row_origin == "bottom":
        mapped = mapped[::-1, :]
    if col_origin == "right":
        mapped = mapped[:, ::-1]
    if transpose:
        mapped = mapped.T
    return mapped


def raw_to_display_rc(row: int, col: int, row_origin: str, col_origin: str, transpose: bool) -> tuple[int, int]:
    mapped_row = 7 - row if row_origin == "bottom" else row
    mapped_col = 7 - col if col_origin == "right" else col
    if transpose:
        return mapped_col, mapped_row
    return mapped_row, mapped_col


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "UNKNOWN"


def raw_to_mv(raw: int, vdda_v: float) -> float:
    return raw * vdda_v * 1000.0 / 65535.0


def parse_frame_line(line: str, active: Optional[dict]) -> tuple[Optional[dict], Optional[list[dict[str, int]]], Optional[str]]:
    text = line.strip()
    if not text:
        return active, None, None
    if text.startswith("FRAME,"):
        parts = text.split(",")
        if len(parts) >= 3:
            try:
                return {"seq": int(parts[1]), "timestamp_us": int(parts[2]), "rows": {}}, None, None
            except ValueError:
                return active, None, f"bad frame line: {text}"
    if active is not None and text.startswith("R") and "," in text:
        parts = text.split(",")
        try:
            row = int(parts[0][1:])
            values = [int(value) for value in parts[1:9]]
        except ValueError:
            return active, None, f"bad row line: {text}"
        if 0 <= row < 8 and len(values) == 8:
            active["rows"][row] = values
        return active, None, None
    if active is not None and text == "END":
        rows = active.get("rows", {})
        if len(rows) != 8:
            return None, None, f"incomplete frame seq={active.get('seq')} rows={sorted(rows.keys())}"
        parsed = []
        for row in range(8):
            values = rows[row]
            parsed.append(
                {
                    "frame": int(active["seq"]),
                    "timestamp_us": int(active["timestamp_us"]),
                    "row": row,
                    **{f"c{col}_raw": values[col] for col in range(8)},
                }
            )
        return None, parsed, None
    return active, None, None


def write_rows(path: Path, rows: list[dict[str, object]], vdda_v: float, condition: str) -> None:
    fields = ["condition", "frame", "timestamp_us", "row"]
    fields += [f"c{i}_raw" for i in range(8)]
    fields += [f"c{i}_mv" for i in range(8)]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            out = {"condition": condition, **row}
            for col in range(8):
                out[f"c{col}_mv"] = f"{raw_to_mv(int(row[f'c{col}_raw']), vdda_v):.3f}"
            writer.writerow(out)


def rows_to_matrix(parsed_rows: list[dict[str, int]], vdda_v: float) -> np.ndarray:
    matrix = np.zeros((8, 8), dtype=float)
    for row in parsed_rows:
        row_id = int(row["row"])
        for col in range(8):
            matrix[row_id, col] = raw_to_mv(int(row[f"c{col}_raw"]), vdda_v)
    return matrix


def capture(args: argparse.Namespace) -> int:
    import serial

    dataset_dir = Path(args.dataset_dir).resolve() if args.dataset_dir else ROOT / "data" / "rebuild_h4" / datetime.now().strftime("%Y%m%d_%H%M%S")
    dataset_dir.mkdir(parents=True, exist_ok=True)
    condition = args.condition.lower()
    csv_path = dataset_dir / f"{condition}.csv"
    raw_log = dataset_dir / f"{condition}_serial_raw.log"
    metadata_path = dataset_dir / "metadata.json"

    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
    else:
        metadata = {
            "order": "ORDER-REBUILD-H4",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "git_commit": git_commit(),
            "port": args.port,
            "baud": args.baud,
            "vdda_v": args.vdda,
            "firmware": "full 8x8 ROW scan, raw output",
            "settle_time_us": 500,
        }
    metadata.setdefault("captures", {})[condition] = {
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "frames_requested": args.frames,
        "note": args.note,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print("ORDER-REBUILD-H4 real sensor capture")
    print(f"Condition: {condition}")
    print(f"Output directory: {dataset_dir}")
    print(f"Opening {args.port} @ {args.baud} ...")

    rows: list[dict[str, object]] = []
    warnings: list[str] = []
    active: Optional[dict] = None
    complete_frames = 0
    first_timestamp: Optional[int] = None
    last_timestamp: Optional[int] = None

    plotter = None
    if args.live:
        import matplotlib.pyplot as plt

        plt.ion()
        fig, ax = plt.subplots(figsize=(5.0, 4.2))
        image = ax.imshow(np.zeros((8, 8)), cmap="viridis", vmin=args.vmin, vmax=args.vmax)
        ax.set_xlabel("Physical X index")
        ax.set_ylabel("Physical Y index")
        ax.set_xticks(range(8))
        ax.set_yticks(range(8))
        colorbar = fig.colorbar(image, ax=ax)
        colorbar.set_label("mV")
        title = ax.set_title("H4 live")
        plotter = (plt, fig, image, title)

    started = time.monotonic()
    timeout = max(args.timeout, args.frames * 0.2 + 20.0)
    with serial.Serial(args.port, args.baud, timeout=0.5) as serial_port, raw_log.open("w", encoding="utf-8", newline="") as log:
        serial_port.reset_input_buffer()
        while complete_frames < args.frames and time.monotonic() - started < timeout:
            raw = serial_port.readline()
            if not raw:
                continue
            line = raw.decode("ascii", errors="ignore").strip()
            log.write(line + "\n")
            active, parsed, warning = parse_frame_line(line, active)
            if warning:
                warnings.append(warning)
            if parsed:
                if first_timestamp is None:
                    first_timestamp = int(parsed[0]["timestamp_us"])
                last_timestamp = int(parsed[0]["timestamp_us"])
                rows.extend(parsed)
                complete_frames += 1
                if plotter is not None:
                    plt, fig, image, title = plotter
                    matrix = rows_to_matrix(parsed, args.vdda)
                    raw_peak_index = np.unravel_index(np.argmax(matrix), matrix.shape)
                    peak_value = matrix[raw_peak_index]
                    display_peak_index = raw_to_display_rc(
                        int(raw_peak_index[0]),
                        int(raw_peak_index[1]),
                        args.row_origin,
                        args.col_origin,
                        args.transpose,
                    )
                    elapsed_s = max(1e-9, time.monotonic() - started)
                    fps = complete_frames / elapsed_s
                    image.set_data(apply_display_map(matrix, args.row_origin, args.col_origin, args.transpose))
                    title.set_text(
                        f"{condition} frame={complete_frames} fps={fps:.1f} "
                        f"peak=X{display_peak_index[1]}Y{display_peak_index[0]} "
                        f"(raw R{raw_peak_index[0]}C{raw_peak_index[1]}) {peak_value:.1f}mV"
                    )
                    fig.canvas.draw_idle()
                    plt.pause(0.001)
                if complete_frames % 50 == 0 or complete_frames == args.frames:
                    print(f"  captured frame {complete_frames}/{args.frames}")

    if not rows:
        raise RuntimeError("No FRAME/R0..R7/END data captured.")
    write_rows(csv_path, rows, args.vdda, condition)
    if warnings:
        (dataset_dir / f"{condition}_capture_warnings.txt").write_text("\n".join(warnings) + "\n", encoding="utf-8")
    if first_timestamp is not None and last_timestamp is not None and last_timestamp > first_timestamp:
        fps = (complete_frames - 1) / ((last_timestamp - first_timestamp) / 1_000_000.0)
    else:
        fps = complete_frames / max(1e-9, time.monotonic() - started)
    print(f"Saved {len(rows)} row records ({complete_frames} frames) -> {csv_path}")
    print(f"Estimated frame rate: {fps:.2f} Hz")
    print(f"Next: python tools/analyze_rebuild_h4.py {dataset_dir}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--condition", choices=["baseline", "single_press", "corner_press", "multi_press"], required=True)
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--frames", type=int, default=500)
    parser.add_argument("--dataset-dir")
    parser.add_argument("--vdda", type=float, default=3.29)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--vmin", type=float, default=1000.0)
    parser.add_argument("--vmax", type=float, default=2500.0)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--note", default="")
    parser.add_argument("--row-origin", choices=["top", "bottom"], default="top", help="physical display location of raw ROW0")
    parser.add_argument("--col-origin", choices=["left", "right"], default="right", help="physical display location of raw COL0")
    parser.add_argument("--transpose", action="store_true", help="swap display X/Y after row/column flips")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(capture(parse_args()))
