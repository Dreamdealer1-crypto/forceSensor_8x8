#!/usr/bin/env python3
"""Unlimited live heatmap display for 8x8 fabric pressure matrix sliding tests.

Expected firmware serial format:

FRAME,<seq>,<timestamp_us>,...
R0,c0,c1,c2,c3,c4,c5,c6,c7
...
R7,c0,c1,c2,c3,c4,c5,c6,c7
END

The script runs until Ctrl+C. It keeps raw data in firmware ROW/COL order and
only remaps the displayed heatmap into physical X/Y coordinates.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Frame:
    seq: int
    timestamp_us: int
    matrix_raw: np.ndarray


def raw_to_mv(raw: int, vdda_v: float) -> float:
    return raw * vdda_v * 1000.0 / 65535.0


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


def parse_serial_frame(serial_port, vdda_v: float) -> Optional[Frame]:
    active = False
    seq = -1
    timestamp_us = 0
    matrix = np.zeros((8, 8), dtype=float)
    rows_seen: set[int] = set()

    while True:
        raw = serial_port.readline()
        if not raw:
            return None
        line = raw.decode("ascii", errors="ignore").strip()
        if not line:
            continue

        if line.startswith("FRAME,"):
            parts = line.split(",")
            if len(parts) >= 3:
                try:
                    seq = int(parts[1])
                    timestamp_us = int(parts[2])
                except ValueError:
                    continue
                active = True
                rows_seen.clear()
                matrix.fill(0.0)
            continue

        if active and line.startswith("R") and "," in line:
            parts = line.split(",")
            if len(parts) < 9:
                continue
            try:
                row = int(parts[0][1:])
                values = [raw_to_mv(int(value), vdda_v) for value in parts[1:9]]
            except ValueError:
                continue
            if 0 <= row < 8:
                matrix[row, :] = values
                rows_seen.add(row)
            continue

        if active and line == "END" and len(rows_seen) == 8:
            return Frame(seq=seq, timestamp_us=timestamp_us, matrix_raw=matrix.copy())


def collect_baseline(serial_port, frame_count: int, vdda_v: float) -> tuple[np.ndarray, np.ndarray]:
    samples = []
    print(f"Collecting baseline: keep sensor unloaded for {frame_count} frames.")
    while len(samples) < frame_count:
        frame = parse_serial_frame(serial_port, vdda_v)
        if frame is None:
            continue
        samples.append(frame.matrix_raw)
        if len(samples) % 25 == 0 or len(samples) == frame_count:
            print(f"  baseline {len(samples)}/{frame_count}")
    stack = np.stack(samples, axis=0)
    return np.mean(stack, axis=0), np.std(stack, axis=0, ddof=1)


def load_baseline(path: Path) -> tuple[np.ndarray, Optional[np.ndarray]]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    mean = np.array(payload["mean_matrix_mv"], dtype=float)
    std = np.array(payload["std_matrix_mv"], dtype=float) if "std_matrix_mv" in payload else None
    if mean.shape != (8, 8):
        raise ValueError(f"baseline mean matrix must be 8x8: {path}")
    return mean, std


def save_baseline(path: Path, mean: np.ndarray, std: np.ndarray, metadata: dict[str, object]) -> None:
    payload = {
        **metadata,
        "mean_matrix_mv": mean.tolist(),
        "std_matrix_mv": std.tolist(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_frame_rows(writer: csv.DictWriter, frame: Frame, matrix_delta: np.ndarray, display_peak: tuple[int, int], raw_peak: tuple[int, int]) -> None:
    for row in range(8):
        out: dict[str, object] = {
            "seq": frame.seq,
            "timestamp_us": frame.timestamp_us,
            "row": row,
            "raw_peak_row": raw_peak[0],
            "raw_peak_col": raw_peak[1],
            "display_peak_y": display_peak[0],
            "display_peak_x": display_peak[1],
        }
        for col in range(8):
            out[f"c{col}_mv"] = f"{frame.matrix_raw[row, col]:.3f}"
            out[f"c{col}_delta_mv"] = f"{matrix_delta[row, col]:.3f}"
        writer.writerow(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--vdda", type=float, default=3.29)
    parser.add_argument("--mode", choices=["delta", "raw"], default="delta")
    parser.add_argument("--baseline-frames", type=int, default=120)
    parser.add_argument("--baseline-json", type=Path, help="load baseline mean/std from JSON")
    parser.add_argument("--save-baseline-json", type=Path, help="save freshly collected baseline JSON")
    parser.add_argument("--save-csv", type=Path, help="optional continuous raw/delta CSV output")
    parser.add_argument("--row-origin", choices=["top", "bottom"], default="top")
    parser.add_argument("--col-origin", choices=["left", "right"], default="right")
    parser.add_argument("--transpose", action="store_true")
    parser.add_argument("--vmin", type=float, default=0.0, help="display minimum; delta mode default 0")
    parser.add_argument("--vmax", type=float, default=1000.0, help="display maximum; delta mode default 1000mV")
    parser.add_argument("--raw-vmin", type=float, default=1000.0)
    parser.add_argument("--raw-vmax", type=float, default=2500.0)
    parser.add_argument("--refresh-every", type=int, default=1, help="update display every N frames")
    parser.add_argument("--peak-threshold", type=float, default=50.0, help="delta threshold for active peak label")
    args = parser.parse_args()

    import matplotlib.pyplot as plt
    import serial

    print("ARCH 1.1 unlimited live pressure heatmap")
    print(f"Port: {args.port} @ {args.baud}")
    print(f"Display map: row_origin={args.row_origin}, col_origin={args.col_origin}, transpose={args.transpose}")
    print("Press Ctrl+C to stop.")

    csv_file = None
    writer = None
    if args.save_csv:
        args.save_csv.parent.mkdir(parents=True, exist_ok=True)
        csv_file = args.save_csv.open("w", encoding="utf-8", newline="")
        fields = ["seq", "timestamp_us", "row", "raw_peak_row", "raw_peak_col", "display_peak_y", "display_peak_x"]
        fields += [f"c{i}_mv" for i in range(8)]
        fields += [f"c{i}_delta_mv" for i in range(8)]
        writer = csv.DictWriter(csv_file, fieldnames=fields)
        writer.writeheader()
        print(f"Saving stream CSV: {args.save_csv}")

    with serial.Serial(args.port, args.baud, timeout=0.5) as serial_port:
        serial_port.reset_input_buffer()

        if args.baseline_json:
            baseline_mean, baseline_std = load_baseline(args.baseline_json)
            print(f"Loaded baseline: {args.baseline_json}")
        else:
            baseline_mean, baseline_std = collect_baseline(serial_port, args.baseline_frames, args.vdda)
            if args.save_baseline_json:
                save_baseline(
                    args.save_baseline_json,
                    baseline_mean,
                    baseline_std,
                    {
                        "created_at": datetime.now().isoformat(timespec="seconds"),
                        "source": "tools/live_rebuild_h4_unlimited.py",
                        "frames": args.baseline_frames,
                        "vdda_v": args.vdda,
                    },
                )
                print(f"Saved baseline: {args.save_baseline_json}")

        display_vmin = args.raw_vmin if args.mode == "raw" else args.vmin
        display_vmax = args.raw_vmax if args.mode == "raw" else args.vmax

        plt.ion()
        fig, ax = plt.subplots(figsize=(6.0, 5.1))
        image = ax.imshow(np.zeros((8, 8)), cmap="viridis", vmin=display_vmin, vmax=display_vmax, aspect="equal")
        ax.set_xlabel("Physical X index")
        ax.set_ylabel("Physical Y index")
        ax.set_xticks(range(8))
        ax.set_yticks(range(8))
        grid_text = [[ax.text(col, row, "", ha="center", va="center", color="white", fontsize=7) for col in range(8)] for row in range(8)]
        colorbar = fig.colorbar(image, ax=ax)
        colorbar.set_label("delta mV" if args.mode == "delta" else "mV")
        title = ax.set_title("Waiting for frames...")

        start_wall = time.monotonic()
        frame_count = 0
        last_seq: Optional[int] = None
        gaps = 0

        try:
            while True:
                frame = parse_serial_frame(serial_port, args.vdda)
                if frame is None:
                    continue
                frame_count += 1
                if last_seq is not None and frame.seq != last_seq + 1:
                    gaps += 1
                last_seq = frame.seq

                delta = frame.matrix_raw - baseline_mean
                metric = delta if args.mode == "delta" else frame.matrix_raw
                raw_peak = tuple(int(value) for value in np.unravel_index(np.nanargmax(delta), delta.shape))
                display_peak = raw_to_display_rc(raw_peak[0], raw_peak[1], args.row_origin, args.col_origin, args.transpose)
                peak_delta = float(delta[raw_peak])
                peak_value = float(frame.matrix_raw[raw_peak])

                if writer is not None:
                    write_frame_rows(writer, frame, delta, display_peak, raw_peak)
                    if frame_count % 50 == 0 and csv_file is not None:
                        csv_file.flush()

                if frame_count % args.refresh_every != 0:
                    continue

                shown = apply_display_map(metric, args.row_origin, args.col_origin, args.transpose)
                image.set_data(shown)
                if args.mode == "delta":
                    image.set_clim(args.vmin, max(args.vmax, min(2500.0, peak_delta * 1.15)))
                for row in range(8):
                    for col in range(8):
                        value = shown[row, col]
                        grid_text[row][col].set_text(f"{value:.0f}" if value >= 10 else "")
                        grid_text[row][col].set_color("white" if value > (display_vmax * 0.45) else "#111111")

                elapsed = max(1e-9, time.monotonic() - start_wall)
                fps = frame_count / elapsed
                active = "ACTIVE" if peak_delta >= args.peak_threshold else "idle"
                title.set_text(
                    f"{args.mode.upper()} seq={frame.seq} fps={fps:.1f} gaps={gaps} "
                    f"peak X{display_peak[1]} Y{display_peak[0]} "
                    f"raw R{raw_peak[0]}C{raw_peak[1]} "
                    f"delta={peak_delta:.1f}mV raw={peak_value:.1f}mV {active}"
                )
                fig.canvas.draw_idle()
                plt.pause(0.001)
        except KeyboardInterrupt:
            print("\nStopped by user.")
        finally:
            if csv_file is not None:
                csv_file.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
