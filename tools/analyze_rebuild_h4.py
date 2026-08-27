#!/usr/bin/env python3
"""Analyze ORDER-REBUILD-H4 real fabric sensor captures."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


CONDITIONS = ["baseline", "single_press", "corner_press", "multi_press"]


def parse_points(text: str) -> list[tuple[int, int]]:
    if not text.strip():
        return []
    points: list[tuple[int, int]] = []
    for item in text.replace(";", " ").split():
        parts = item.split(",")
        if len(parts) != 2:
            raise ValueError(f"bad point '{item}', expected row,col")
        row, col = int(parts[0]), int(parts[1])
        if not (0 <= row < 8 and 0 <= col < 8):
            raise ValueError(f"point out of range: {item}")
        points.append((row, col))
    return points


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


def set_plot_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["Times New Roman", "DejaVu Serif", "STIXGeneral"],
            "font.size": 8,
            "axes.labelsize": 8,
            "axes.titlesize": 9,
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
            "legend.fontsize": 7,
            "axes.linewidth": 0.8,
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
        }
    )


def load_capture(path: Path) -> tuple[np.ndarray, np.ndarray]:
    rows = list(csv.DictReader(path.open("r", encoding="utf-8-sig", newline="")))
    if not rows:
        raise RuntimeError(f"empty capture: {path}")
    frame_ids = sorted({int(row["frame"]) for row in rows})
    frame_index = {frame: index for index, frame in enumerate(frame_ids)}
    data = np.full((len(frame_ids), 8, 8), np.nan, dtype=float)
    timestamps = np.zeros(len(frame_ids), dtype=float)
    for row in rows:
        fi = frame_index[int(row["frame"])]
        ri = int(row["row"])
        timestamps[fi] = float(row["timestamp_us"]) / 1_000_000.0
        for col in range(8):
            data[fi, ri, col] = float(row[f"c{col}_mv"])
    timestamps -= timestamps[0]
    return data, timestamps


def save_heatmap(
    path: Path,
    matrix: np.ndarray,
    title: str,
    vmin: float | None = None,
    vmax: float | None = None,
    label: str = "mV",
    xlabel: str = "X index",
    ylabel: str = "Y index",
) -> None:
    fig, ax = plt.subplots(figsize=(4.2, 3.3), constrained_layout=True)
    image = ax.imshow(matrix, cmap="viridis", vmin=vmin, vmax=vmax, aspect="equal")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.set_xticks(range(8))
    ax.set_yticks(range(8))
    for row in range(8):
        for col in range(8):
            ax.text(col, row, f"{matrix[row, col]:.0f}", ha="center", va="center", fontsize=5.5, color="white")
    colorbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    colorbar.set_label(label)
    fig.savefig(path.with_suffix(".svg"), format="svg")
    fig.savefig(path.with_suffix(".png"), dpi=300)
    plt.close(fig)


def peak_delta_summary(data: np.ndarray, baseline: np.ndarray) -> dict[str, object]:
    deltas = data - baseline[None, :, :]
    peak_flat = int(np.nanargmax(deltas))
    frame, row, col = np.unravel_index(peak_flat, deltas.shape)
    peak_delta = float(deltas[frame, row, col])
    peak_value = float(data[frame, row, col])
    return {
        "peak_frame_index": int(frame),
        "peak_row": int(row),
        "peak_col": int(col),
        "peak_value_mv": peak_value,
        "peak_delta_mv": peak_delta,
        "peak_delta_matrix": deltas[frame].tolist(),
    }


def frame_rate_from_timestamps(timestamps: np.ndarray) -> float | None:
    return (len(timestamps) - 1) / (timestamps[-1] - timestamps[0]) if len(timestamps) > 1 and timestamps[-1] > timestamps[0] else None


def window_peak_delta(data: np.ndarray, baseline: np.ndarray, start: int, stop: int) -> dict[str, object]:
    stop = min(stop, data.shape[0])
    start = max(0, min(start, stop - 1))
    summary = peak_delta_summary(data[start:stop], baseline)
    summary["peak_frame_index"] = int(summary["peak_frame_index"]) + start
    summary["window_start_frame"] = start
    summary["window_stop_frame"] = stop
    return summary


def save_corner_grid(
    path: Path,
    data: np.ndarray,
    timestamps: np.ndarray,
    baseline: np.ndarray,
    frame_rate: float,
    row_origin: str,
    col_origin: str,
    transpose: bool,
) -> list[dict[str, object]]:
    windows_s = [(0, 4), (4, 8), (8, 12), (12, 16)]
    labels = ["top-left", "top-right", "bottom-left", "bottom-right"]
    summaries = []
    fig, axes = plt.subplots(2, 2, figsize=(5.4, 4.7), constrained_layout=True)
    vmax = 100.0
    matrices = []
    for label, (start_s, stop_s) in zip(labels, windows_s):
        start = int(round(start_s * frame_rate))
        stop = int(round(stop_s * frame_rate))
        summary = window_peak_delta(data, baseline, start, stop)
        matrix = np.array(summary["peak_delta_matrix"], dtype=float)
        matrices.append(matrix)
        vmax = max(vmax, float(np.nanmax(matrix)))
        display_row, display_col = raw_to_display_rc(int(summary["peak_row"]), int(summary["peak_col"]), row_origin, col_origin, transpose)
        summaries.append(
            {
                "label": label,
                "peak_row": int(summary["peak_row"]),
                "peak_col": int(summary["peak_col"]),
                "display_y": display_row,
                "display_x": display_col,
                "peak_delta_mv": float(summary["peak_delta_mv"]),
            }
        )
    for ax, label, matrix in zip(axes.ravel(), labels, matrices):
        shown = apply_display_map(matrix, row_origin, col_origin, transpose)
        image = ax.imshow(shown, cmap="viridis", vmin=0, vmax=vmax, aspect="equal")
        ax.set_title(label)
        ax.set_xlabel("X index")
        ax.set_ylabel("Y index")
        ax.set_xticks(range(8))
        ax.set_yticks(range(8))
    fig.colorbar(image, ax=axes.ravel().tolist(), fraction=0.035, pad=0.02, label="Delta (mV)")
    fig.savefig(path.with_suffix(".svg"), format="svg")
    fig.savefig(path.with_suffix(".png"), dpi=300)
    plt.close(fig)
    return summaries


def save_arch04_summary(
    path: Path,
    baseline_mean: np.ndarray,
    single_delta: np.ndarray | None,
    single_trace: tuple[np.ndarray, np.ndarray, float] | None,
    corner_grid_path: Path | None,
    multi_delta: np.ndarray | None,
    row_origin: str,
    col_origin: str,
    transpose: bool,
) -> None:
    fig = plt.figure(figsize=(9.6, 5.4), constrained_layout=True)
    grid = fig.add_gridspec(2, 3, height_ratios=[1.0, 0.9])
    axes = [fig.add_subplot(grid[0, i]) for i in range(3)]
    ax_trace = fig.add_subplot(grid[1, :2])
    ax_note = fig.add_subplot(grid[1, 2])

    panels = [
        ("Baseline", apply_display_map(baseline_mean, row_origin, col_origin, transpose), 1000, 1100, "mV"),
        ("Single press delta", apply_display_map(single_delta, row_origin, col_origin, transpose) if single_delta is not None else None, 0, None, "Delta mV"),
        ("Multi press delta", apply_display_map(multi_delta, row_origin, col_origin, transpose) if multi_delta is not None else None, 0, None, "Delta mV"),
    ]
    for ax, (title, matrix, vmin, vmax, label) in zip(axes, panels):
        if matrix is None:
            ax.axis("off")
            ax.set_title(title + " (pending)")
            continue
        if vmax is None:
            vmax = max(100.0, float(np.nanmax(matrix)))
        image = ax.imshow(matrix, cmap="viridis", vmin=vmin, vmax=vmax, aspect="equal")
        ax.set_title(title)
        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        ax.set_xticks(range(8))
        ax.set_yticks(range(8))
        fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04, label=label)

    if single_trace is not None:
        timestamps, trace, baseline_value = single_trace
        ax_trace.plot(timestamps, trace, color="#24568f", linewidth=1.1)
        ax_trace.axhline(baseline_value, color="#9b3d3d", linestyle="--", linewidth=0.9)
        ax_trace.set_title("Single press dynamic response")
        ax_trace.set_xlabel("Time (s)")
        ax_trace.set_ylabel("Output voltage (mV)")
        ax_trace.grid(True, color="#d9d9d9", linewidth=0.5)
    else:
        ax_trace.axis("off")
        ax_trace.set_title("Single press dynamic response (pending)")

    ax_note.axis("off")
    ax_note.text(
        0.0,
        0.95,
        "Physical display map\n"
        f"row_origin={row_origin}\n"
        f"col_origin={col_origin}\n"
        f"transpose={transpose}\n\n"
        "Raw data remain in\n"
        "firmware ROW/COL order.",
        va="top",
        fontsize=9,
    )
    fig.savefig(path.with_suffix(".svg"), format="svg")
    fig.savefig(path.with_suffix(".png"), dpi=300)
    plt.close(fig)


def save_multi_known_points(
    figure_dir: Path,
    data: np.ndarray,
    timestamps: np.ndarray,
    baseline_mean: np.ndarray,
    baseline_noise: np.ndarray,
    points: list[tuple[int, int]],
    row_origin: str,
    col_origin: str,
    transpose: bool,
) -> list[dict[str, object]]:
    if not points:
        return []
    deltas = data - baseline_mean[None, :, :]
    summaries: list[dict[str, object]] = []
    fig, ax = plt.subplots(figsize=(5.4, 3.0), constrained_layout=True)
    colors = ["#24568f", "#d28b26", "#4f8f3a", "#9b3d3d", "#6b5ca5"]
    for index, (row, col) in enumerate(points):
        trace = data[:, row, col]
        delta_trace = deltas[:, row, col]
        peak_index = int(np.nanargmax(delta_trace))
        display_y, display_x = raw_to_display_rc(row, col, row_origin, col_origin, transpose)
        peak_delta = float(delta_trace[peak_index])
        summaries.append(
            {
                "raw_row": row,
                "raw_col": col,
                "display_y": display_y,
                "display_x": display_x,
                "peak_frame_index": peak_index,
                "peak_delta_mv": peak_delta,
                "peak_value_mv": float(trace[peak_index]),
                "snr": float(peak_delta / max(float(baseline_noise[row, col]), 1e-6)),
            }
        )
        ax.plot(timestamps, delta_trace, linewidth=1.1, color=colors[index % len(colors)], label=f"R{row}C{col} / X{display_x}Y{display_y}")
    ax.axhline(50.0, color="#9b3d3d", linestyle="--", linewidth=0.9, label="50 mV")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Delta from baseline (mV)")
    ax.set_title("Multi-press known point responses")
    ax.grid(True, color="#d9d9d9", linewidth=0.5)
    ax.legend(frameon=False, ncol=2)
    fig.savefig(figure_dir / "multi_press_known_points_timeseries.svg", format="svg")
    fig.savefig(figure_dir / "multi_press_known_points_timeseries.png", dpi=300)
    plt.close(fig)

    peak_frames = [item["peak_frame_index"] for item in summaries]
    representative = int(round(float(np.median(peak_frames))))
    matrix = apply_display_map(deltas[representative], row_origin, col_origin, transpose)
    save_heatmap(
        figure_dir / "multi_press_known_points_delta_heatmap",
        matrix,
        "H4 multi-press known points delta",
        0,
        max(100.0, float(np.nanmax(matrix))),
        "Delta (mV)",
    )
    return summaries


def analyze(dataset_dir: Path, row_origin: str, col_origin: str, transpose: bool, multi_points: list[tuple[int, int]]) -> dict[str, object]:
    set_plot_style()
    figure_dir = dataset_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, object] = {
        "order": "ORDER-REBUILD-H4",
        "dataset_dir": str(dataset_dir),
        "conditions": {},
        "display_map": {"row_origin": row_origin, "col_origin": col_origin, "transpose": transpose},
    }

    captures: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for condition in CONDITIONS:
        path = dataset_dir / f"{condition}.csv"
        if path.exists():
            captures[condition] = load_capture(path)

    if "baseline" not in captures:
        raise RuntimeError("baseline.csv is required before H4 analysis.")

    baseline_data, baseline_t = captures["baseline"]
    baseline_mean = np.nanmean(baseline_data, axis=0)
    baseline_std = np.nanstd(baseline_data, axis=0, ddof=1)
    baseline_min = np.nanmin(baseline_data, axis=0)
    baseline_max = np.nanmax(baseline_data, axis=0)
    frame_rate = frame_rate_from_timestamps(baseline_t)
    baseline_stats = {
        "frames": int(baseline_data.shape[0]),
        "frame_rate_hz": frame_rate,
        "mean_min_mv": float(np.nanmin(baseline_mean)),
        "mean_max_mv": float(np.nanmax(baseline_mean)),
        "max_std_mv": float(np.nanmax(baseline_std)),
        "all_mean_in_1020_1060": bool(np.all((baseline_mean >= 1020.0) & (baseline_mean <= 1060.0))),
        "all_std_lt_10": bool(np.all(baseline_std < 10.0)),
        "mean_matrix_mv": baseline_mean.tolist(),
        "std_matrix_mv": baseline_std.tolist(),
        "min_matrix_mv": baseline_min.tolist(),
        "max_matrix_mv": baseline_max.tolist(),
    }
    result["baseline"] = baseline_stats
    display_baseline_mean = apply_display_map(baseline_mean, row_origin, col_origin, transpose)
    display_baseline_std = apply_display_map(baseline_std, row_origin, col_origin, transpose)
    save_heatmap(figure_dir / "baseline_heatmap", display_baseline_mean, "H4 baseline mean", 1000, 1100)
    save_heatmap(figure_dir / "baseline_std_heatmap", display_baseline_std, "H4 baseline noise SD", 0, max(10.0, float(np.nanmax(baseline_std))), "SD (mV)")

    fig, axes = plt.subplots(1, 2, figsize=(6.4, 2.7), constrained_layout=True)
    axes[0].plot(range(8), np.nanmean(baseline_mean, axis=1), marker="o", color="#24568f")
    axes[0].set_xlabel("Row")
    axes[0].set_ylabel("Mean baseline (mV)")
    axes[0].set_title("Row mean")
    axes[0].grid(True, color="#d9d9d9", linewidth=0.5)
    axes[1].plot(range(8), np.nanmean(baseline_mean, axis=0), marker="o", color="#d28b26")
    axes[1].set_xlabel("Column")
    axes[1].set_ylabel("Mean baseline (mV)")
    axes[1].set_title("Column mean")
    axes[1].grid(True, color="#d9d9d9", linewidth=0.5)
    fig.savefig(figure_dir / "baseline_row_col_mean.svg", format="svg")
    fig.savefig(figure_dir / "baseline_row_col_mean.png", dpi=300)
    plt.close(fig)

    baseline_noise = np.maximum(baseline_std, 1e-6)
    single_delta_for_summary = None
    single_trace_for_summary = None
    multi_delta_for_summary = None
    for condition in ["single_press", "corner_press", "multi_press"]:
        if condition not in captures:
            continue
        data, timestamps = captures[condition]
        summary = peak_delta_summary(data, baseline_mean)
        peak_matrix = np.array(summary["peak_delta_matrix"], dtype=float)
        peak_row = int(summary["peak_row"])
        peak_col = int(summary["peak_col"])
        snr = float(summary["peak_delta_mv"] / baseline_noise[peak_row, peak_col])
        summary["snr"] = snr
        summary["frames"] = int(data.shape[0])
        result[condition] = {key: value for key, value in summary.items() if key != "peak_delta_matrix"}
        display_peak_row, display_peak_col = raw_to_display_rc(peak_row, peak_col, row_origin, col_origin, transpose)
        result[condition]["display_y"] = display_peak_row
        result[condition]["display_x"] = display_peak_col
        display_peak_matrix = apply_display_map(peak_matrix, row_origin, col_origin, transpose)
        display_raw_matrix = apply_display_map(data[int(summary["peak_frame_index"])], row_origin, col_origin, transpose)
        save_heatmap(figure_dir / f"{condition}_delta_heatmap", display_peak_matrix, f"H4 {condition} peak delta", 0, max(100.0, float(np.nanmax(peak_matrix))), "Delta (mV)")
        save_heatmap(figure_dir / f"{condition}_raw_heatmap", display_raw_matrix, f"H4 {condition} peak raw", 1000, max(1500.0, float(np.nanmax(data))), "mV")

        trace = data[:, peak_row, peak_col]
        fig, ax = plt.subplots(figsize=(5.2, 2.8), constrained_layout=True)
        ax.plot(timestamps, trace, color="#24568f", linewidth=1.1)
        ax.axhline(baseline_mean[peak_row, peak_col], color="#9b3d3d", linestyle="--", linewidth=0.9, label="baseline")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Output voltage (mV)")
        ax.set_title(f"{condition}: peak R{peak_row}C{peak_col}")
        ax.grid(True, color="#d9d9d9", linewidth=0.5)
        ax.legend(frameon=False)
        fig.savefig(figure_dir / f"{condition}_timeseries.svg", format="svg")
        fig.savefig(figure_dir / f"{condition}_timeseries.png", dpi=300)
        plt.close(fig)
        if condition == "single_press":
            single_delta_for_summary = peak_matrix
            single_trace_for_summary = (timestamps, trace, float(baseline_mean[peak_row, peak_col]))
        if condition == "multi_press":
            multi_delta_for_summary = peak_matrix
            known = save_multi_known_points(
                figure_dir,
                data,
                timestamps,
                baseline_mean,
                baseline_noise,
                multi_points,
                row_origin,
                col_origin,
                transpose,
            )
            if known:
                result[condition]["known_points"] = known
        if condition == "corner_press":
            capture_rate = frame_rate_from_timestamps(timestamps) or frame_rate or 15.0
            result[condition]["corner_windows"] = save_corner_grid(
                figure_dir / "corner_press_delta_grid",
                data,
                timestamps,
                baseline_mean,
                capture_rate,
                row_origin,
                col_origin,
                transpose,
            )

    save_arch04_summary(
        figure_dir / "h4_arch04_summary",
        baseline_mean,
        single_delta_for_summary,
        single_trace_for_summary,
        figure_dir / "corner_press_delta_grid.svg" if "corner_press" in result else None,
        multi_delta_for_summary,
        row_origin,
        col_origin,
        transpose,
    )

    result["status"] = "PARTIAL"
    if baseline_stats["all_mean_in_1020_1060"] and baseline_stats["all_std_lt_10"]:
        result["status"] = "BASELINE_PASS"
    if "single_press" in result and float(result["single_press"]["peak_delta_mv"]) > 50.0:
        result["status"] = "RESPONSE_OBSERVED"
    if all(key in result for key in ["single_press", "corner_press", "multi_press"]):
        result["status"] = "READY_FOR_H4_REVIEW"

    (dataset_dir / "baseline_stats.json").write_text(json.dumps(baseline_stats, indent=2), encoding="utf-8")
    (dataset_dir / "analysis_summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_dir", type=Path)
    parser.add_argument("--row-origin", choices=["top", "bottom"], default="top", help="physical display location of raw ROW0")
    parser.add_argument("--col-origin", choices=["left", "right"], default="left", help="physical display location of raw COL0")
    parser.add_argument("--transpose", action="store_true", help="swap display X/Y after row/column flips")
    parser.add_argument("--multi-points", default="", help="known raw multi-press points, e.g. '1,2 4,6 6,2'")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = analyze(args.dataset_dir.resolve(), args.row_origin, args.col_origin, args.transpose, parse_points(args.multi_points))
    print("ORDER-REBUILD-H4 ANALYSIS")
    print(f"STATUS: {result['status']}")
    baseline = result["baseline"]
    print(f"Baseline mean range: {baseline['mean_min_mv']:.3f}mV ~ {baseline['mean_max_mv']:.3f}mV")
    print(f"Baseline max std: {baseline['max_std_mv']:.3f}mV")
    for condition in ["single_press", "corner_press", "multi_press"]:
        if condition in result:
            item = result[condition]
            print(
                f"{condition}: peak=R{item['peak_row']}C{item['peak_col']} "
                f"display=Y{item['display_y']}X{item['display_x']} "
                f"delta={item['peak_delta_mv']:.3f}mV SNR={item['snr']:.1f}"
            )
            if condition == "multi_press" and item.get("known_points"):
                for point in item["known_points"]:
                    print(
                        f"  known R{point['raw_row']}C{point['raw_col']} "
                        f"display=Y{point['display_y']}X{point['display_x']} "
                        f"delta={point['peak_delta_mv']:.3f}mV SNR={point['snr']:.1f}"
                    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
