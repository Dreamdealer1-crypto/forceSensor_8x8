#!/usr/bin/env python3
"""Capture continuous force-ramp response for one 8x8 taxel position.

The firmware is expected to keep the H4 8x8 ROW scan text protocol:

    FRAME,<seq>,<timestamp_us>,1030
    R0,c0,c1,...,c7
    ...
    R7,c0,...,c7
    END

The script provides a manual start/stop switch from the terminal:
press Enter once to start recording, press Enter again to stop.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import queue
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[2]


class LivePlotter:
    def __init__(self, target: tuple[int, int], refresh_every: int, vdda_v: float) -> None:
        import matplotlib.pyplot as plt
        import numpy as np

        self.plt = plt
        self.np = np
        self.target = target
        self.refresh_every = max(1, refresh_every)
        self.vdda_v = vdda_v
        self.times: list[float] = []
        self.target_values: list[float] = []
        self.baseline: Optional[float] = None

        plt.ion()
        self.fig, (self.ax_trace, self.ax_heatmap) = plt.subplots(1, 2, figsize=(9.5, 4.0), constrained_layout=True)
        (self.trace_line,) = self.ax_trace.plot([], [], color="#1f77b4", linewidth=1.4)
        self.ax_trace.set_xlabel("Elapsed time (s)")
        self.ax_trace.set_ylabel(f"R{target[0]}C{target[1]} raw delta")
        self.ax_trace.grid(True, alpha=0.25)
        self.image = self.ax_heatmap.imshow(np.zeros((8, 8)), cmap="viridis", aspect="equal")
        self.ax_heatmap.set_title("8x8 raw delta heatmap")
        self.ax_heatmap.set_xlabel("Column")
        self.ax_heatmap.set_ylabel("Row")
        self.ax_heatmap.set_xticks(range(8))
        self.ax_heatmap.set_yticks(range(8))
        self.fig.colorbar(self.image, ax=self.ax_heatmap, fraction=0.046, pad=0.04, label="raw delta")
        self.fig.canvas.draw_idle()
        plt.pause(0.001)

    def update(self, frame: dict, elapsed_s: float, frame_count: int) -> None:
        if frame_count % self.refresh_every != 0:
            return
        matrix = self.np.asarray(frame["matrix"], dtype=float)
        tr, tc = self.target
        value = float(matrix[tr, tc])
        if self.baseline is None:
            self.baseline = value
            self.baseline_matrix = matrix.copy()
        delta_matrix = matrix - self.baseline_matrix
        delta_value = value - self.baseline
        self.times.append(elapsed_s)
        self.target_values.append(delta_value)

        self.trace_line.set_data(self.times, self.target_values)
        self.ax_trace.set_xlim(0.0, max(1.0, self.times[-1]))
        ymin = min(self.target_values)
        ymax = max(self.target_values)
        pad = max(5.0, (ymax - ymin) * 0.1)
        self.ax_trace.set_ylim(ymin - pad, ymax + pad)

        self.image.set_data(delta_matrix)
        vmax = float(self.np.nanmax(self.np.abs(delta_matrix)))
        vmax = max(vmax, 1.0)
        self.image.set_clim(-vmax, vmax)
        self.ax_heatmap.set_title(f"8x8 raw delta heatmap | frame {frame_count}")
        self.fig.canvas.draw_idle()
        self.plt.pause(0.001)


def raw_to_mv(raw: int, vdda_v: float) -> float:
    return raw * vdda_v * 1000.0 / 65535.0


def parse_frame_line(line: str, active: Optional[dict]) -> tuple[Optional[dict], Optional[dict], Optional[str]]:
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
        matrix = [[int(rows[row][col]) for col in range(8)] for row in range(8)]
        return None, {"seq": int(active["seq"]), "timestamp_us": int(active["timestamp_us"]), "matrix": matrix}, None
    return active, None, None


def keyboard_worker(events: queue.Queue[str]) -> None:
    input()
    events.put("start")
    input()
    events.put("stop")


def make_fieldnames(include_mv: bool, estimate_force: bool) -> list[str]:
    fields = [
        "experiment",
        "condition",
        "repeat",
        "grid_row",
        "grid_col",
        "ramp_rate_N_s",
        "elapsed_s",
        "frame_seq",
        "timestamp_ms",
        "host_time_s",
    ]
    if estimate_force:
        fields.insert(fields.index("frame_seq"), "force_N_est")
    fields += [f"r{r}c{c}_raw" for r in range(8) for c in range(8)]
    if include_mv:
        fields += [f"r{r}c{c}_mv" for r in range(8) for c in range(8)]
    return fields


def synthetic_frame(index: int, target: tuple[int, int], baseline_raw: int = 20500) -> dict:
    row0, col0 = target
    force = index * 0.2 / 16.0
    matrix = []
    for row in range(8):
        values = []
        for col in range(8):
            distance2 = (row - row0) ** 2 + (col - col0) ** 2
            response = 1200.0 * force * math.exp(-distance2 / 1.2)
            values.append(int(baseline_raw + response + 8.0 * math.sin(index * 0.31 + row + col)))
        matrix.append(values)
    return {"seq": index, "timestamp_us": index * 62500, "matrix": matrix}


def frame_to_row(frame: dict, args: argparse.Namespace, start_host_time: float, include_mv: bool) -> dict[str, object]:
    elapsed = max(0.0, time.monotonic() - start_host_time)
    out: dict[str, object] = {
        "experiment": args.experiment,
        "condition": args.condition,
        "repeat": args.repeat,
        "grid_row": args.grid_row,
        "grid_col": args.grid_col,
        "ramp_rate_N_s": args.ramp_rate,
        "elapsed_s": f"{elapsed:.6f}",
        "frame_seq": frame["seq"],
        "timestamp_ms": f"{frame['timestamp_us'] / 1000.0:.3f}",
        "host_time_s": f"{time.time():.6f}",
    }
    if args.estimate_force:
        out["force_N_est"] = f"{args.start_force_n + args.ramp_rate * elapsed:.6f}"
    matrix = frame["matrix"]
    for row in range(8):
        for col in range(8):
            raw = int(matrix[row][col])
            out[f"r{row}c{col}_raw"] = raw
            if include_mv:
                out[f"r{row}c{col}_mv"] = f"{raw_to_mv(raw, args.vdda):.3f}"
    return out


def summarize(rows: list[dict[str, object]], target: tuple[int, int], dropped: int) -> dict[str, object]:
    if not rows:
        return {"frames": 0, "dropped_frames": dropped}
    target_key = f"r{target[0]}c{target[1]}_raw"
    target_values = [int(row[target_key]) for row in rows]
    elapsed = float(rows[-1]["elapsed_s"]) - float(rows[0]["elapsed_s"]) if len(rows) > 1 else 0.0
    fps = (len(rows) - 1) / elapsed if elapsed > 0 else 0.0
    return {
        "frames": len(rows),
        "frame_rate_hz": fps,
        "dropped_frames": dropped,
        "target_raw_min": min(target_values),
        "target_raw_max": max(target_values),
        "target_raw_delta": target_values[-1] - target_values[0],
    }


def safe_name(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in text.strip())
    return cleaned.strip("_") or "run"


def make_run_dir(args: argparse.Namespace) -> Path:
    if args.dataset_dir:
        base_dir = Path(args.dataset_dir).resolve()
    else:
        base_dir = ROOT / "data" / "phase2" / "force_ramp"

    if args.overwrite_dataset_dir:
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_name = f"{timestamp}_R{args.grid_row}C{args.grid_col}_{safe_name(args.condition)}"
    candidate = base_dir / run_name
    suffix = 1
    while candidate.exists():
        candidate = base_dir / f"{run_name}_{suffix:03d}"
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def capture(args: argparse.Namespace) -> int:
    if args.duration is not None and args.duration <= 0:
        raise ValueError("--duration must be positive")
    if args.frames is not None and args.frames <= 0:
        raise ValueError("--frames must be positive")

    dataset_dir = make_run_dir(args)
    csv_path = dataset_dir / "force_ramp.csv"
    raw_log_path = dataset_dir / "serial_raw.log"
    metadata_path = dataset_dir / "metadata.json"
    warning_path = dataset_dir / "warnings.txt"

    print("Force-ramp capture for 8x8 matrix")
    print(f"Target taxel: R{args.grid_row}C{args.grid_col}")
    print(f"Ramp rate: {args.ramp_rate:.6g} N/s")
    print(f"Output: {csv_path}")
    print(f"Run directory: {dataset_dir}")
    if args.dry_run:
        print("Mode: DRY-RUN")
    else:
        print(f"Serial: {args.port} @ {args.baud}")
    print()
    print("Press Enter to START recording.")
    print("Press Enter again to STOP recording.")

    events: queue.Queue[str] = queue.Queue()
    if not args.auto_start:
        threading.Thread(target=keyboard_worker, args=(events,), daemon=True).start()
        while events.get() != "start":
            pass

    start_host_time = time.monotonic()
    print(f"START {datetime.now().isoformat(timespec='seconds')}")

    rows: list[dict[str, object]] = []
    warnings: list[str] = []
    active: Optional[dict] = None
    last_seq: Optional[int] = None
    dropped = 0
    include_mv = not args.no_mv
    fieldnames = make_fieldnames(include_mv, args.estimate_force)
    plotter = LivePlotter((args.grid_row, args.grid_col), args.plot_every, args.vdda) if args.live_plot else None

    with csv_path.open("w", encoding="utf-8", newline="") as csv_file, raw_log_path.open("w", encoding="utf-8", newline="") as raw_log:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        if args.dry_run:
            index = 0
            while True:
                if not args.auto_start and not events.empty() and events.get() == "stop":
                    break
                if args.duration is not None and time.monotonic() - start_host_time >= args.duration:
                    break
                if args.frames is not None and len(rows) >= args.frames:
                    break
                frame = synthetic_frame(index, (args.grid_row, args.grid_col))
                row = frame_to_row(frame, args, start_host_time, include_mv)
                writer.writerow(row)
                rows.append(row)
                if plotter is not None:
                    plotter.update(frame, float(row["elapsed_s"]), len(rows))
                index += 1
                time.sleep(1.0 / args.dry_run_hz)
        else:
            import serial

            with serial.Serial(args.port, args.baud, timeout=0.25) as serial_port:
                serial_port.reset_input_buffer()
                while True:
                    if not args.auto_start and not events.empty() and events.get() == "stop":
                        break
                    if args.duration is not None and time.monotonic() - start_host_time >= args.duration:
                        break
                    if args.frames is not None and len(rows) >= args.frames:
                        break
                    raw = serial_port.readline()
                    if not raw:
                        continue
                    line = raw.decode("ascii", errors="ignore").strip()
                    raw_log.write(line + "\n")
                    active, frame, warning = parse_frame_line(line, active)
                    if warning:
                        warnings.append(warning)
                    if frame is None:
                        continue
                    seq = int(frame["seq"])
                    if last_seq is not None and seq != last_seq + 1:
                        gap = seq - last_seq - 1
                        if gap > 0:
                            dropped += gap
                            warnings.append(f"sequence gap: previous={last_seq} current={seq} dropped={gap}")
                            print(f"WARNING: dropped {gap} frame(s), seq {last_seq}->{seq}")
                    last_seq = seq
                    row = frame_to_row(frame, args, start_host_time, include_mv)
                    writer.writerow(row)
                    rows.append(row)
                    if plotter is not None:
                        plotter.update(frame, float(row["elapsed_s"]), len(rows))
                    if args.live_text and len(rows) % args.live_every == 0:
                        target_key = f"r{args.grid_row}c{args.grid_col}_raw"
                        print(
                            f"frames={len(rows)} elapsed={row['elapsed_s']}s "
                            f"target_raw={row[target_key]}"
                        )

    summary = summarize(rows, (args.grid_row, args.grid_col), dropped)
    metadata = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).relative_to(ROOT)),
        "experiment": args.experiment,
        "condition": args.condition,
        "repeat": args.repeat,
        "grid_row": args.grid_row,
        "grid_col": args.grid_col,
        "ramp_rate_N_s": args.ramp_rate,
        "force_values": "not_recorded; align with compression-instrument force log offline",
        "estimate_force_column_enabled": args.estimate_force,
        "start_force_N": args.start_force_n,
        "port": None if args.dry_run else args.port,
        "baud": args.baud,
        "vdda_v": args.vdda,
        "csv": csv_path.name,
        "raw_log": raw_log_path.name,
        "summary": summary,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    if warnings:
        warning_path.write_text("\n".join(warnings) + "\n", encoding="utf-8")

    print(f"STOP {datetime.now().isoformat(timespec='seconds')}")
    print("Capture summary")
    for key, value in summary.items():
        print(f"  {key}: {value}")
    print(f"  metadata: {metadata_path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", default="force_ramp")
    parser.add_argument("--condition", default="ramp_0p2N_s")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--grid-row", type=int, required=True)
    parser.add_argument("--grid-col", type=int, required=True)
    parser.add_argument("--ramp-rate", type=float, default=0.2, help="Force ramp rate in N/s.")
    parser.add_argument("--start-force-n", type=float, default=0.0)
    parser.add_argument("--estimate-force", action="store_true", help="Add force_N_est column from ramp rate and elapsed time.")
    parser.add_argument("--duration", type=float, help="Optional automatic stop after seconds.")
    parser.add_argument("--frames", type=int, help="Optional automatic stop after complete frames.")
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--vdda", type=float, default=3.29)
    parser.add_argument("--dataset-dir")
    parser.add_argument(
        "--overwrite-dataset-dir",
        action="store_true",
        help="Use --dataset-dir directly instead of creating a timestamped child directory.",
    )
    parser.add_argument("--auto-start", action="store_true", help="Start immediately; stop by --duration/--frames or Ctrl+C.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dry-run-hz", type=float, default=16.0)
    parser.add_argument("--no-mv", action="store_true", help="Only store raw ADC columns.")
    parser.add_argument("--live-text", action="store_true")
    parser.add_argument("--live-every", type=int, default=10)
    parser.add_argument("--live-plot", action="store_true", help="Show target trace and 8x8 heatmap inside this capture process.")
    parser.add_argument("--plot-every", type=int, default=5, help="Refresh live plot every N captured frames.")
    args = parser.parse_args()
    if not (0 <= args.grid_row < 8 and 0 <= args.grid_col < 8):
        raise ValueError("--grid-row/--grid-col must be in [0, 7]")
    return args


if __name__ == "__main__":
    raise SystemExit(capture(parse_args()))
