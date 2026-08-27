#!/usr/bin/env python3
"""Live 8x8 pressure heatmap for the resistive matrix project.

The STM32 firmware is expected to output frames in the existing RAW format:

FRAME,<seq>,<timestamp_us>,<vref_mv>
R0,<c0>,...,<c7>
...
R7,<c0>,...,<c7>
END

This host program performs baseline subtraction and displays a relative
pressure heatmap. It intentionally reports a relative pressure score unless
the user supplies a calibrated full-scale reference.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = time.strftime("%Y-%m-%d_order-live-pressure_run01")


@dataclass
class MatrixFrame:
    seq: int
    timestamp_us: int
    matrix: np.ndarray
    phase: str = "LIVE"
    index: int = 0


class SerialFrameSource:
    def __init__(self, port: str, baud: int, timeout: float) -> None:
        import serial

        self.serial = serial.Serial(port, baud, timeout=timeout)
        self.serial.reset_input_buffer()

    def close(self) -> None:
        self.serial.close()

    def read_frame(self) -> MatrixFrame:
        active = False
        seq = -1
        timestamp_us = 0
        matrix = np.zeros((8, 8), dtype=float)
        rows_seen = set()

        while True:
            raw = self.serial.readline()
            if not raw:
                raise TimeoutError("Timed out waiting for serial frame.")
            line = raw.decode("ascii", errors="ignore").strip()
            if not line:
                continue

            if line.startswith("FRAME,"):
                parts = line.split(",")
                if len(parts) >= 3:
                    seq = int(parts[1])
                    timestamp_us = int(parts[2])
                    active = True
                    rows_seen.clear()
                    matrix.fill(0)
                continue

            if active and line.startswith("R"):
                parts = line.split(",")
                if len(parts) != 9:
                    continue
                row = int(parts[0][1:])
                if 0 <= row < 8:
                    matrix[row, :] = [float(value) for value in parts[1:]]
                    rows_seen.add(row)
                continue

            if active and line == "END" and len(rows_seen) == 8:
                return MatrixFrame(seq=seq, timestamp_us=timestamp_us, matrix=matrix.copy())


class ReplayFrameSource:
    def __init__(self, csv_path: Path) -> None:
        self.frames = self._load(csv_path)
        if not self.frames:
            raise ValueError(f"No frames found in replay CSV: {csv_path}")
        self.pos = 0

    @staticmethod
    def _load(csv_path: Path) -> list[MatrixFrame]:
        grouped: dict[int, dict[str, object]] = {}
        with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                index = int(row["index"])
                item = grouped.setdefault(
                    index,
                    {
                        "seq": int(row["frame_seq"]),
                        "timestamp_us": int(row["timestamp_us"]),
                        "phase": row.get("phase", "REPLAY"),
                        "matrix": np.zeros((8, 8), dtype=float),
                    },
                )
                r = int(row["row"])
                c = int(row["col"])
                # For replay, the demo frames CSV already contains delta.
                item["matrix"][r, c] = float(row["delta"])  # type: ignore[index]

        frames = []
        for index in sorted(grouped):
            item = grouped[index]
            frames.append(
                MatrixFrame(
                    seq=int(item["seq"]),
                    timestamp_us=int(item["timestamp_us"]),
                    matrix=np.array(item["matrix"], dtype=float),
                    phase=str(item["phase"]),
                    index=index,
                )
            )
        return frames

    def close(self) -> None:
        return None

    def read_frame(self) -> MatrixFrame:
        frame = self.frames[self.pos]
        self.pos = (self.pos + 1) % len(self.frames)
        return frame


def collect_baseline(source: SerialFrameSource, frame_count: int) -> tuple[np.ndarray, np.ndarray]:
    samples = []
    print(f"Collecting baseline: keep sensor unloaded for {frame_count} frames.")
    for index in range(frame_count):
        frame = source.read_frame()
        samples.append(frame.matrix)
        if (index + 1) % 10 == 0 or index == frame_count - 1:
            print(f"  baseline {index + 1}/{frame_count}")
    stack = np.stack(samples, axis=0)
    return stack.mean(axis=0), stack.std(axis=0, ddof=1)


def load_replay_threshold(csv_path: Path, threshold_min: float) -> np.ndarray:
    thresholds = np.full((8, 8), threshold_min, dtype=float)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            r = int(row["row"])
            c = int(row["col"])
            if "threshold_counts" in row and row["threshold_counts"]:
                thresholds[r, c] = float(row["threshold_counts"])
    return thresholds


def pressure_label(score: float) -> str:
    if score < 10:
        return "idle"
    if score < 35:
        return "light"
    if score < 70:
        return "medium"
    return "heavy"


def find_peaks(
    clipped: np.ndarray,
    thresholds: np.ndarray,
    max_points: int,
    suppress_radius: int,
) -> list[dict[str, float | int]]:
    candidates = []
    for row in range(8):
        for col in range(8):
            value = float(clipped[row, col])
            if value <= float(thresholds[row, col]):
                continue

            row0 = max(0, row - 1)
            row1 = min(8, row + 2)
            col0 = max(0, col - 1)
            col1 = min(8, col + 2)
            if value < float(np.max(clipped[row0:row1, col0:col1])):
                continue

            candidates.append({"row": row, "col": col, "delta": value})

    candidates.sort(key=lambda item: float(item["delta"]), reverse=True)
    peaks: list[dict[str, float | int]] = []
    for candidate in candidates:
        too_close = False
        for peak in peaks:
            if max(
                abs(int(candidate["row"]) - int(peak["row"])),
                abs(int(candidate["col"]) - int(peak["col"])),
            ) <= suppress_radius:
                too_close = True
                break
        if too_close:
            continue
        peaks.append(candidate)
        if len(peaks) >= max_points:
            break
    return peaks


def analyze_delta(
    delta: np.ndarray,
    thresholds: np.ndarray,
    full_scale_delta: float,
    max_points: int,
    suppress_radius: int,
) -> dict[str, object]:
    clipped = np.maximum(delta, 0)
    peak_flat = int(np.argmax(clipped))
    peak_row, peak_col = divmod(peak_flat, 8)
    max_delta = float(clipped[peak_row, peak_col])
    pressed = clipped > thresholds
    pressed_count = int(np.count_nonzero(pressed))
    score = 0.0 if full_scale_delta <= 0 else min(100.0, max(0.0, max_delta / full_scale_delta * 100.0))
    peaks = find_peaks(clipped, thresholds, max_points, suppress_radius)
    active = len(peaks) > 0

    if pressed_count:
        weights = clipped * pressed
        total = float(weights.sum())
        rows, cols = np.indices((8, 8))
        center_row = float((rows * weights).sum() / total)
        center_col = float((cols * weights).sum() / total)
    else:
        center_row = float(peak_row)
        center_col = float(peak_col)

    return {
        "display": clipped,
        "active": active,
        "peak_row": int(peaks[0]["row"]) if active else -1,
        "peak_col": int(peaks[0]["col"]) if active else -1,
        "max_delta": float(peaks[0]["delta"]) if active else 0.0,
        "raw_max_delta": max_delta,
        "pressed_count": pressed_count,
        "score": score if active else 0.0,
        "label": pressure_label(score) if active else "idle",
        "center_row": center_row,
        "center_col": center_col,
        "peaks": peaks,
    }


def append_summary(csv_path: Path, frame: MatrixFrame, analysis: dict[str, object]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    exists = csv_path.exists()
    with csv_path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "time_s",
                "phase",
                "frame_seq",
                "source_index",
                "active",
                "max_row",
                "max_col",
                "max_delta",
                "raw_max_delta",
                "pressed_pixel_count",
                "pressure_score_pct",
                "pressure_label",
                "center_row",
                "center_col",
                "peaks",
            ],
        )
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "time_s": f"{time.time():.3f}",
                "phase": frame.phase,
                "frame_seq": frame.seq,
                "source_index": frame.index,
                "active": analysis["active"],
                "max_row": analysis["peak_row"],
                "max_col": analysis["peak_col"],
                "max_delta": f"{float(analysis['max_delta']):.3f}",
                "raw_max_delta": f"{float(analysis['raw_max_delta']):.3f}",
                "pressed_pixel_count": analysis["pressed_count"],
                "pressure_score_pct": f"{float(analysis['score']):.2f}",
                "pressure_label": analysis["label"],
                "center_row": f"{float(analysis['center_row']):.3f}",
                "center_col": f"{float(analysis['center_col']):.3f}",
                "peaks": ";".join(
                    f"R{int(peak['row'])}/C{int(peak['col'])}:{float(peak['delta']):.0f}"
                    for peak in analysis["peaks"]  # type: ignore[index]
                ),
            }
        )


def render_frame(
    ax,
    image,
    markers,
    frame: MatrixFrame,
    analysis: dict[str, object],
    full_scale_delta: float,
    fps: float,
) -> None:
    image.set_data(analysis["display"])
    peaks = analysis["peaks"]  # type: ignore[assignment]
    for marker_index, marker in enumerate(markers):
        if marker_index < len(peaks):
            peak = peaks[marker_index]
            marker.center = (float(peak["col"]), float(peak["row"]))
            marker.set_visible(True)
        else:
            marker.set_visible(False)

    if analysis["active"]:
        peak_text = "; ".join(
            f"R{int(peak['row'])}/C{int(peak['col'])}:{float(peak['delta']):.0f}"
            for peak in peaks[:3]
        )
    else:
        peak_text = "none"

    ax.set_title(
        "Frame {idx} | {phase} | max_delta={delta:.0f} | pressure={score:.1f}% ({label})\nPeaks: {peaks}".format(
            idx=frame.index if frame.phase != "LIVE" else frame.seq,
            phase=frame.phase,
            peaks=peak_text,
            delta=float(analysis["max_delta"]),
            score=float(analysis["score"]),
            label=analysis["label"],
        ),
        fontsize=10,
    )
    if fps > 0:
        ax.set_xlabel(f"FPS: {fps:.1f} | z = re-zero baseline | c = clear display | close window = stop")
    else:
        ax.set_xlabel("z = re-zero baseline | c = clear display | close window = stop")
    ax.figure.canvas.draw_idle()


def build_plot(full_scale_delta: float, max_points: int):
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle

    fig, ax = plt.subplots(figsize=(8.0, 7.0))
    image = ax.imshow(
        np.zeros((8, 8), dtype=float),
        vmin=0,
        vmax=full_scale_delta,
        cmap="inferno",
        origin="upper",
        interpolation="nearest",
    )
    ax.set_xticks(range(8), labels=[f"C{i}" for i in range(8)])
    ax.set_yticks(range(8), labels=[f"R{i}" for i in range(8)])
    ax.set_xticks(np.arange(-0.5, 8, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, 8, 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=0.8, alpha=0.65)
    ax.tick_params(which="minor", bottom=False, left=False)
    colors = ["#00e5ff", "#00ff66", "#ff3df2"]
    markers = []
    for index in range(max_points):
        marker = Circle(
            (0, 0),
            radius=0.38 + index * 0.06,
            fill=False,
            edgecolor=colors[index % len(colors)],
            linewidth=2.5,
            visible=False,
        )
        ax.add_patch(marker)
        markers.append(marker)
    colorbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    colorbar.set_label(f"delta counts, fixed scale 0..{full_scale_delta:.0f}")
    fig.tight_layout(rect=[0, 0.02, 1, 0.98])
    return fig, ax, image, markers


def save_preview(args: argparse.Namespace, source: ReplayFrameSource, thresholds: np.ndarray) -> None:
    import matplotlib

    matplotlib.use("Agg")
    output = Path(args.save_preview)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame = max(source.frames, key=lambda item: float(np.max(item.matrix)))
    analysis = analyze_delta(frame.matrix, thresholds, args.full_scale_delta, args.max_points, args.suppress_radius)
    fig, ax, image, markers = build_plot(args.full_scale_delta, args.max_points)
    render_frame(ax, image, markers, frame, analysis, args.full_scale_delta, 0.0)
    fig.savefig(output, dpi=160)
    print(f"Saved preview: {output}")


def run_display(args: argparse.Namespace) -> None:
    import matplotlib.pyplot as plt

    if args.replay_csv:
        replay_path = Path(args.replay_csv)
        source: SerialFrameSource | ReplayFrameSource = ReplayFrameSource(replay_path)
        baseline = np.zeros((8, 8), dtype=float)
        std = np.zeros((8, 8), dtype=float)
        thresholds = load_replay_threshold(replay_path, args.threshold_min)
    else:
        source = SerialFrameSource(args.port, args.baud, args.timeout)
        baseline, std = collect_baseline(source, args.baseline_frames)
        thresholds = np.maximum(args.threshold_sigma * std, args.threshold_min)

    try:
        fig, ax, image, markers = build_plot(args.full_scale_delta, args.max_points)
        summary_csv = ROOT / "data" / "csv" / f"{args.run}_live_pressure_summary.csv"
        display_delta = np.zeros((8, 8), dtype=float)
        frame_index = 0
        fps = 0.0
        fps_start_wall = time.perf_counter()
        fps_start_frames = 0
        control = {"rezero": False, "clear": False}

        def on_key(event) -> None:
            if event.key == "z":
                control["rezero"] = True
            elif event.key == "c":
                control["clear"] = True

        fig.canvas.mpl_connect("key_press_event", on_key)

        print("Live heatmap started. Close the plot window or press Ctrl+C to stop.")
        print("Keys in heatmap window: z = re-zero baseline, c = clear display.")
        while plt.fignum_exists(fig.number):
            frame = source.read_frame()
            frame.index = frame_index
            if args.replay_csv:
                raw_delta = frame.matrix
            else:
                raw_delta = frame.matrix - baseline

            if control["rezero"] and not args.replay_csv:
                baseline = frame.matrix.copy()
                display_delta.fill(0)
                raw_delta = frame.matrix - baseline
                control["rezero"] = False
                print("Baseline re-zeroed from current frame.")

            if control["clear"]:
                display_delta.fill(0)
                control["clear"] = False
                print("Display cleared.")

            raw_delta = np.maximum(raw_delta, 0)
            raw_analysis = analyze_delta(raw_delta, thresholds, args.full_scale_delta, args.max_points, args.suppress_radius)

            if not args.replay_csv and not raw_analysis["active"]:
                baseline = (1.0 - args.auto_zero_rate) * baseline + args.auto_zero_rate * frame.matrix
                raw_delta = np.maximum(frame.matrix - baseline, 0)

            if args.attack >= 1.0 and args.release >= 1.0:
                display_delta = raw_delta
            else:
                rising = raw_delta >= display_delta
                display_delta = np.where(
                    rising,
                    args.attack * raw_delta + (1.0 - args.attack) * display_delta,
                    args.release * raw_delta + (1.0 - args.release) * display_delta,
                )
                if not raw_analysis["active"]:
                    display_delta *= args.idle_decay

            now = time.perf_counter()
            if now - fps_start_wall >= 1.0:
                fps = (frame_index - fps_start_frames) / (now - fps_start_wall)
                fps_start_wall = now
                fps_start_frames = frame_index
            analysis = analyze_delta(display_delta, thresholds, args.full_scale_delta, args.max_points, args.suppress_radius)
            render_frame(ax, image, markers, frame, analysis, args.full_scale_delta, fps)
            if args.log_every > 0 and frame_index % args.log_every == 0:
                append_summary(summary_csv, frame, analysis)

            if args.print_summary:
                print(
                    "Frame {idx:05d} {phase:8s} active={active!s:5s} Peak R{row}/C{col} "
                    "max_delta={delta:8.1f} pressure={score:5.1f}% pressed={pressed}".format(
                        idx=frame_index,
                        phase=frame.phase,
                        active=analysis["active"],
                        row=analysis["peak_row"],
                        col=analysis["peak_col"],
                        delta=float(analysis["max_delta"]),
                        score=float(analysis["score"]),
                        pressed=analysis["pressed_count"],
                    )
                )

            plt.pause(args.interval)
            frame_index += 1
    finally:
        source.close()


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Live 8x8 pressure heatmap viewer.")
    parser.add_argument("--port", default="COM7", help="Serial port for STM32 VCP.")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate.")
    parser.add_argument("--timeout", type=float, default=2.0, help="Serial read timeout in seconds.")
    parser.add_argument("--baseline-frames", type=int, default=100, help="Frames used for unloaded baseline.")
    parser.add_argument("--threshold-sigma", type=float, default=2.5, help="Pressed threshold multiplier for baseline std.")
    parser.add_argument("--threshold-min", type=float, default=60.0, help="Minimum pressed threshold in ADC counts.")
    parser.add_argument("--full-scale-delta", type=float, default=18000.0, help="Delta counts treated as 100 percent relative pressure.")
    parser.add_argument("--attack", type=float, default=1.0, help="Display filter attack factor, 0..1. Higher appears faster.")
    parser.add_argument("--release", type=float, default=1.0, help="Display filter release factor, 0..1. Higher disappears faster.")
    parser.add_argument("--idle-decay", type=float, default=0.0, help="Extra display decay multiplier when no active pressure is detected.")
    parser.add_argument("--auto-zero-rate", type=float, default=0.0, help="Slow baseline tracking rate while idle.")
    parser.add_argument("--max-points", type=int, default=3, help="Maximum independent pressure peaks to mark.")
    parser.add_argument("--suppress-radius", type=int, default=1, help="Peak non-maximum suppression radius in cells.")
    parser.add_argument("--interval", type=float, default=0.001, help="Display update pause in seconds.")
    parser.add_argument("--log-every", type=int, default=5, help="Append one summary row every N frames; use 0 to disable logging.")
    parser.add_argument("--run", default=DEFAULT_RUN, help="Run id for live summary CSV.")
    parser.add_argument("--print-summary", action="store_true", help="Print per-frame peak summary in terminal.")
    parser.add_argument("--replay-csv", help="Replay an existing ORDER-DEMO-001 frames CSV instead of serial input.")
    parser.add_argument("--save-preview", help="Save one peak-frame preview PNG from replay CSV and exit.")
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    args.attack = min(1.0, max(0.0, args.attack))
    args.release = min(1.0, max(0.0, args.release))
    args.idle_decay = min(1.0, max(0.0, args.idle_decay))
    args.auto_zero_rate = min(1.0, max(0.0, args.auto_zero_rate))
    args.max_points = max(1, min(3, args.max_points))
    args.suppress_radius = max(0, args.suppress_radius)

    if args.save_preview:
        if not args.replay_csv:
            print("--save-preview requires --replay-csv", file=sys.stderr)
            return 2
        source = ReplayFrameSource(Path(args.replay_csv))
        thresholds = load_replay_threshold(Path(args.replay_csv), args.threshold_min)
        save_preview(args, source, thresholds)
        return 0

    run_display(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
