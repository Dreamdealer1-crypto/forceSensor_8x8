#!/usr/bin/env python3
"""Generate four report SVGs for force-ramp run 1 at R4C3."""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


STYLE = {
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
    "savefig.bbox": "tight",
}


@dataclass
class ForceRun:
    label: str
    start_text: str
    start_epoch_s: float
    time_s: np.ndarray
    force_n: np.ndarray


def save_svg(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, format="svg")
    plt.close(fig)


def load_first_force_run(path: Path) -> ForceRun:
    raw = pd.read_excel(path, sheet_name=0, header=None)
    block = raw.iloc[:, 0:10]
    title = str(block.iloc[0, 0])
    match = re.search(r"测试编号:([^ ]+)\s+(.*)$", title)
    label = match.group(1) if match else "run1"
    start_text = match.group(2) if match else ""
    start_epoch = datetime.strptime(start_text, "%Y-%m-%d %H:%M:%S.%f").timestamp()
    headers = [str(x).strip() for x in block.iloc[8].tolist()]
    force_col = headers.index("N") if "N" in headers else 1
    time_col = headers.index("sec") if "sec" in headers else 3
    data = block.iloc[9:]
    time_s = pd.to_numeric(data.iloc[:, time_col], errors="coerce").to_numpy(float)
    force_n = pd.to_numeric(data.iloc[:, force_col], errors="coerce").to_numpy(float)
    mask = np.isfinite(time_s) & np.isfinite(force_n)
    time_s = time_s[mask]
    force_n = force_n[mask]
    time_s -= time_s[0]
    return ForceRun(label, start_text, start_epoch, time_s, force_n)


def load_matrix(csv_path: Path, target: tuple[int, int]) -> dict[str, np.ndarray]:
    df = pd.read_csv(csv_path)
    tr, tc = target
    target_key = f"r{tr}c{tc}_raw"
    elapsed_s = pd.to_numeric(df["elapsed_s"], errors="coerce").to_numpy(float)
    elapsed_s -= np.nanmin(elapsed_s)
    host_time_s = pd.to_numeric(df["host_time_s"], errors="coerce").to_numpy(float)
    target_raw = pd.to_numeric(df[target_key], errors="coerce").to_numpy(float)
    raw_cols = [f"r{r}c{c}_raw" for r in range(8) for c in range(8)]
    stack = df[raw_cols].apply(pd.to_numeric, errors="coerce").to_numpy(float).reshape((-1, 8, 8))
    baseline_n = max(10, min(60, len(target_raw) // 25))
    baseline = float(np.nanmedian(target_raw[:baseline_n]))
    baseline_matrix = np.nanmedian(stack[:baseline_n], axis=0)
    return {
        "elapsed_s": elapsed_s,
        "host_time_s": host_time_s,
        "target_raw": target_raw,
        "target_delta": target_raw - baseline,
        "delta_stack": stack - baseline_matrix,
    }


def filter_signal(values: np.ndarray, window: int = 31) -> np.ndarray:
    series = pd.Series(values).interpolate(limit_direction="both")
    median = series.rolling(window=7, center=True, min_periods=1).median()
    smooth = median.rolling(window=window, center=True, min_periods=1).mean()
    return smooth.to_numpy(float)


def align_force(force: ForceRun, matrix: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    adc_peak_idx = int(np.nanargmax(matrix["target_delta"]))
    adc_peak_time = float(matrix["elapsed_s"][adc_peak_idx])
    force_peak_time = float(force.time_s[int(np.nanargmax(force.force_n))])
    shifted_force_time = matrix["elapsed_s"] - (adc_peak_time - force_peak_time)
    mask = (shifted_force_time >= force.time_s[0]) & (shifted_force_time <= force.time_s[-1])
    t = matrix["elapsed_s"][mask]
    f = np.interp(shifted_force_time[mask], force.time_s, force.force_n)
    return t, f, mask


def binned_trend(x: np.ndarray, y: np.ndarray, bins: int = 28) -> tuple[np.ndarray, np.ndarray]:
    edges = np.linspace(np.nanmin(x), np.nanmax(x), bins + 1)
    centers = []
    medians = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        mask = (x >= lo) & (x < hi)
        if np.sum(mask) >= 3:
            centers.append((lo + hi) / 2.0)
            medians.append(float(np.nanmedian(y[mask])))
    return np.asarray(centers), np.asarray(medians)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-xls", default="data/phase2/force_ramp/R3C3_40N/20260827-01.xls")
    parser.add_argument("--matrix-csv", default="data/phase2/force_ramp/R3C3_40N/20260827_002209_R3C3_ramp_0p2N_s/force_ramp.csv")
    parser.add_argument("--output-dir", default="data/phase2/force_ramp/R3C3_40N/analysis_R4C3_run1")
    parser.add_argument("--target-row", type=int, default=4)
    parser.add_argument("--target-col", type=int, default=3)
    parser.add_argument("--diameter-mm", type=float, default=4.0)
    args = parser.parse_args()

    plt.rcParams.update(STYLE)
    force = load_first_force_run(Path(args.force_xls))
    matrix = load_matrix(Path(args.matrix_csv), (args.target_row, args.target_col))
    t, f_n, mask = align_force(force, matrix)
    full_t = matrix["elapsed_s"]
    full_raw = matrix["target_delta"]
    full_filtered = filter_signal(full_raw)
    raw = matrix["target_delta"][mask]
    raw_filtered = filter_signal(raw)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(5.2, 3.2), constrained_layout=True)
    ax.plot(full_t, full_raw, color="#1f77b4", linewidth=0.8)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Raw delta")
    ax.set_title("Raw Data")
    ax.grid(True, alpha=0.25)
    save_svg(fig, output / "01_raw_data.svg")

    fig, ax1 = plt.subplots(figsize=(5.6, 3.2), constrained_layout=True)
    ax2 = ax1.twinx()
    l1 = ax1.plot(full_t, full_filtered, color="#1f77b4", linewidth=1.0, label="Filtered ADC")[0]
    l2 = ax2.plot(t, f_n, color="#d62728", linewidth=1.0, label="Force")[0]
    ax1.set_xlabel("Time (s)")
    ax1.set_ylabel("Filtered raw delta")
    ax2.set_ylabel("Force (N)")
    ax1.set_title("Filtered ADC and Force")
    ax1.grid(True, alpha=0.25)
    ax1.legend([l1, l2], [l1.get_label(), l2.get_label()], frameon=False, loc="best")
    save_svg(fig, output / "02_filtered_force_overlay.svg")

    fig, ax = plt.subplots(figsize=(4.6, 3.4), constrained_layout=True)
    ax.scatter(raw_filtered, f_n, s=10, alpha=0.4, color="#1f77b4", edgecolors="none", label="samples")
    bx, by = binned_trend(raw_filtered, f_n)
    if len(bx) > 1:
        ax.plot(bx, by, color="#d62728", linewidth=1.4, label="binned median")
        ax.legend(frameon=False)
    ax.set_xlabel("Filtered raw delta")
    ax.set_ylabel("Force (N)")
    ax.set_title("F-ADC Response")
    ax.grid(True, alpha=0.25)
    save_svg(fig, output / "03_force_adc_response.svg")

    peak_local = int(np.nanargmax(np.abs(raw_filtered)))
    global_indices = np.flatnonzero(mask)
    peak_global = int(global_indices[peak_local])
    heat = matrix["delta_stack"][peak_global]
    fig = plt.figure(figsize=(5.0, 4.0), constrained_layout=True)
    ax = fig.add_subplot(111, projection="3d")
    vmax = max(1.0, float(np.nanmax(np.abs(heat))))
    xx, yy = np.meshgrid(np.arange(8), np.arange(8))
    surf = ax.plot_surface(xx, yy, heat, cmap="RdBu_r", vmin=-vmax, vmax=vmax, linewidth=0.4, edgecolor="0.35", alpha=0.92)
    ax.scatter([args.target_col], [args.target_row], [heat[args.target_row, args.target_col]], color="black", s=24)
    ax.set_xlabel("Column")
    ax.set_ylabel("Row")
    ax.set_zlabel("Raw delta")
    ax.set_title("Peak 3D Heatmap")
    ax.set_xticks(range(8))
    ax.set_yticks(range(8))
    for r in range(8):
        for c in range(8):
            ax.text(c, r, heat[r, c], f"{heat[r, c]:.0f}", fontsize=5.0, ha="center")
    fig.colorbar(surf, ax=ax, fraction=0.046, pad=0.04, label="raw delta")
    save_svg(fig, output / "04_peak_3d_heatmap_values.svg")

    fig, axes = plt.subplots(3, 3, figsize=(7.2, 5.8), sharex=True, constrained_layout=True)
    center_r, center_c = args.target_row, args.target_col
    y_min = float("inf")
    y_max = float("-inf")
    traces: dict[tuple[int, int], np.ndarray] = {}
    for rr in range(center_r - 1, center_r + 2):
        for cc in range(center_c - 1, center_c + 2):
            trace = matrix["delta_stack"][:, rr, cc][mask]
            filtered = filter_signal(trace)
            traces[(rr, cc)] = filtered
            y_min = min(y_min, float(np.nanmin(filtered)))
            y_max = max(y_max, float(np.nanmax(filtered)))
    y_pad = max(10.0, 0.08 * (y_max - y_min))
    for ax_r, rr in enumerate(range(center_r - 1, center_r + 2)):
        for ax_c, cc in enumerate(range(center_c - 1, center_c + 2)):
            ax = axes[ax_r, ax_c]
            color = "#d62728" if (rr, cc) == (center_r, center_c) else "#1f77b4"
            ax.plot(t, traces[(rr, cc)], color=color, linewidth=1.0)
            ax.set_title(f"R{rr}C{cc}", color=color)
            ax.grid(True, alpha=0.22)
            ax.set_ylim(y_min - y_pad, y_max + y_pad)
            if ax_r == 2:
                ax.set_xlabel("Time (s)")
            if ax_c == 0:
                ax.set_ylabel("Filtered raw delta")
    fig.suptitle("3x3 Neighbor Trends", fontsize=10)
    save_svg(fig, output / "05_3x3_neighbor_trends.svg")

    result = {
        "force_xls": str(Path(args.force_xls).resolve()),
        "matrix_csv": str(Path(args.matrix_csv).resolve()),
        "target": {"row": args.target_row, "col": args.target_col},
        "diameter_mm": args.diameter_mm,
        "max_force_N": float(np.nanmax(f_n)),
        "samples_aligned": int(len(t)),
        "alignment": "event_peak: compression force peak aligned to R4C3 ADC peak",
        "outputs": [
            "01_raw_data.svg",
            "02_filtered_force_overlay.svg",
            "03_force_adc_response.svg",
            "04_peak_3d_heatmap_values.svg",
            "05_3x3_neighbor_trends.svg",
        ],
    }
    (output / "R4C3_run1_results.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved report SVGs -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
