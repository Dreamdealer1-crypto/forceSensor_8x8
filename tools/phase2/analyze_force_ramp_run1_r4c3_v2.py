#!/usr/bin/env python3
"""Regenerate R4C3 run-1 force-ramp report with contact-onset alignment."""

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
    "font.size": 9,
    "axes.labelsize": 9,
    "axes.titlesize": 10,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
    "axes.linewidth": 0.8,
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
    "savefig.bbox": "tight",
}


@dataclass
class ForceRun:
    label: str
    start_text: str
    time_s: np.ndarray
    force_n: np.ndarray


def save_svg(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, format="svg")
    plt.close(fig)


def filter_signal(values: np.ndarray, median_window: int = 7, mean_window: int = 31) -> np.ndarray:
    series = pd.Series(values).interpolate(limit_direction="both")
    median = series.rolling(window=median_window, center=True, min_periods=1).median()
    smooth = median.rolling(window=mean_window, center=True, min_periods=1).mean()
    return smooth.to_numpy(float)


def load_first_force_run(path: Path) -> ForceRun:
    raw = pd.read_excel(path, sheet_name=0, header=None)
    block = raw.iloc[:, 0:10]
    title = str(block.iloc[0, 0])
    match = re.search(r"测试编号:([^ ]+)\s+(.*)$", title)
    label = match.group(1) if match else "run1"
    start_text = match.group(2) if match else ""
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
    return ForceRun(label, start_text, time_s, force_n)


def load_matrix(csv_path: Path, target: tuple[int, int]) -> dict[str, np.ndarray]:
    df = pd.read_csv(csv_path)
    tr, tc = target
    target_key = f"r{tr}c{tc}_raw"
    elapsed_s = pd.to_numeric(df["elapsed_s"], errors="coerce").to_numpy(float)
    elapsed_s -= np.nanmin(elapsed_s)
    target_raw = pd.to_numeric(df[target_key], errors="coerce").to_numpy(float)
    raw_cols = [f"r{r}c{c}_raw" for r in range(8) for c in range(8)]
    stack = df[raw_cols].apply(pd.to_numeric, errors="coerce").to_numpy(float).reshape((-1, 8, 8))
    baseline_n = max(10, min(60, len(target_raw) // 25))
    baseline = float(np.nanmedian(target_raw[:baseline_n]))
    baseline_matrix = np.nanmedian(stack[:baseline_n], axis=0)
    target_delta = target_raw - baseline
    return {
        "elapsed_s": elapsed_s,
        "target_delta": target_delta,
        "target_filtered": filter_signal(target_delta),
        "delta_stack": stack - baseline_matrix,
    }


def first_crossing(values: np.ndarray, threshold: float, start: int = 0) -> int:
    hits = np.flatnonzero((np.arange(len(values)) >= start) & (values > threshold))
    if len(hits) == 0:
        return 0
    return int(hits[0])


def detect_events(force: ForceRun, matrix: dict[str, np.ndarray]) -> dict[str, float | int]:
    adc = matrix["target_filtered"]
    adc_noise = float(np.nanstd(adc[:100]))
    adc_thr = max(300.0, 5.0 * adc_noise)
    adc_contact_i = first_crossing(adc, adc_thr)
    adc_peak_i = int(np.nanargmax(adc))
    post = np.flatnonzero((np.arange(len(adc)) > adc_peak_i) & (adc < adc_thr))
    adc_release_i = int(post[0]) if len(post) else len(adc) - 1

    force_noise = float(np.nanstd(force.force_n[:20]))
    force_thr = max(0.5, float(np.nanmedian(force.force_n[:20]) + 5.0 * force_noise))
    force_contact_i = first_crossing(force.force_n, force_thr)
    force_peak_i = int(np.nanargmax(force.force_n))

    return {
        "adc_threshold": adc_thr,
        "adc_contact_i": adc_contact_i,
        "adc_contact_s": float(matrix["elapsed_s"][adc_contact_i]),
        "adc_peak_i": adc_peak_i,
        "adc_peak_s": float(matrix["elapsed_s"][adc_peak_i]),
        "adc_release_i": adc_release_i,
        "adc_release_s": float(matrix["elapsed_s"][adc_release_i]),
        "force_threshold": force_thr,
        "force_contact_i": force_contact_i,
        "force_contact_s": float(force.time_s[force_contact_i]),
        "force_peak_i": force_peak_i,
        "force_peak_s": float(force.time_s[force_peak_i]),
    }


def align_by_contact(force: ForceRun, matrix: dict[str, np.ndarray], events: dict[str, float | int]) -> tuple[np.ndarray, np.ndarray]:
    shift = float(events["adc_contact_s"]) - float(events["force_contact_s"])
    force_on_matrix_time = matrix["elapsed_s"] - shift
    force_interp = np.full_like(matrix["elapsed_s"], np.nan, dtype=float)
    mask = (force_on_matrix_time >= force.time_s[0]) & (force_on_matrix_time <= force.time_s[-1])
    force_interp[mask] = np.interp(force_on_matrix_time[mask], force.time_s, force.force_n)
    return force_interp, mask


def binned_median(x: np.ndarray, y: np.ndarray, bins: int = 30) -> tuple[np.ndarray, np.ndarray]:
    finite = np.isfinite(x) & np.isfinite(y)
    x = x[finite]
    y = y[finite]
    edges = np.linspace(float(np.min(x)), float(np.max(x)), bins + 1)
    centers, medians = [], []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        mask = (x >= lo) & (x < hi)
        if np.sum(mask) >= 3:
            centers.append((lo + hi) / 2.0)
            medians.append(float(np.median(y[mask])))
    return np.asarray(centers), np.asarray(medians)


def fit_models(adc: np.ndarray, force: np.ndarray) -> dict[str, object]:
    mask = np.isfinite(adc) & np.isfinite(force)
    mask &= adc > np.nanpercentile(adc[mask], 5)
    x = adc[mask]
    y = force[mask]
    out: dict[str, object] = {}
    if len(x) >= 5:
        p1 = np.polyfit(x, y, 1)
        y1 = np.polyval(p1, x)
        p2 = np.polyfit(x, y, 2)
        y2 = np.polyval(p2, x)
        def r2(pred: np.ndarray) -> float:
            ss_res = float(np.sum((y - pred) ** 2))
            ss_tot = float(np.sum((y - np.mean(y)) ** 2))
            return 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
        out = {
            "linear": {"coef": [float(v) for v in p1], "r2": r2(y1)},
            "quadratic": {"coef": [float(v) for v in p2], "r2": r2(y2)},
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-xls", default="data/phase2/force_ramp/R3C3_40N/20260827-01.xls")
    parser.add_argument("--matrix-csv", default="data/phase2/force_ramp/R3C3_40N/20260827_002209_R3C3_ramp_0p2N_s/force_ramp.csv")
    parser.add_argument("--output-dir", default="data/phase2/force_ramp/R3C3_40N/analysis_R4C3_run1_v2")
    parser.add_argument("--target-row", type=int, default=4)
    parser.add_argument("--target-col", type=int, default=3)
    args = parser.parse_args()

    plt.rcParams.update(STYLE)
    output = Path(args.output_dir)
    target = (args.target_row, args.target_col)
    force = load_first_force_run(Path(args.force_xls))
    matrix = load_matrix(Path(args.matrix_csv), target)
    events = detect_events(force, matrix)
    force_aligned, force_mask = align_by_contact(force, matrix, events)

    adc = matrix["target_delta"]
    adc_f = matrix["target_filtered"]
    t = matrix["elapsed_s"]
    crop_start = max(0.0, float(events["adc_contact_s"]) - 8.0)
    crop_stop = min(float(t[-1]), float(events["adc_release_s"]) + 6.0)
    crop = (t >= crop_start) & (t <= crop_stop)

    # 01 full raw, with cropped working region and event markers.
    fig, ax = plt.subplots(figsize=(6.2, 3.4), constrained_layout=True)
    ax.plot(t, adc, color="#4C78A8", linewidth=0.8, label="raw")
    ax.axvspan(crop_start, crop_stop, color="#F2CF5B", alpha=0.18, label="used window")
    ax.axvline(float(events["adc_contact_s"]), color="#54A24B", linestyle="--", linewidth=1.0, label="ADC contact")
    ax.axvline(float(events["adc_peak_s"]), color="#E45756", linestyle="--", linewidth=1.0, label="ADC peak")
    ax.set_xlabel("Matrix time (s)")
    ax.set_ylabel("Raw delta")
    ax.set_title("Raw Data")
    ax.grid(True, alpha=0.25)
    ax.legend(frameon=False)
    save_svg(fig, output / "01_raw_data_full.svg")

    # 02 filtered ADC and force, contact-aligned.
    fig, ax1 = plt.subplots(figsize=(6.2, 3.4), constrained_layout=True)
    ax2 = ax1.twinx()
    l1 = ax1.plot(t[crop], adc_f[crop], color="#4C78A8", linewidth=1.4, label="filtered ADC")[0]
    l2 = ax2.plot(t[crop], force_aligned[crop], color="#E45756", linestyle="--", linewidth=1.2, label="force")[0]
    ax1.axvline(float(events["adc_contact_s"]), color="#54A24B", linestyle=":", linewidth=1.0)
    ax1.axvline(float(events["adc_peak_s"]), color="#333333", linestyle=":", linewidth=1.0)
    ax1.set_xlabel("Matrix time (s)")
    ax1.set_ylabel("Filtered raw delta")
    ax2.set_ylabel("Force (N)")
    ax1.set_title("Filtered ADC and Force")
    ax1.grid(True, alpha=0.25)
    ax1.legend([l1, l2], [l1.get_label(), l2.get_label()], frameon=False, loc="best")
    save_svg(fig, output / "02_filtered_force_overlay.svg")

    # 03 F-ADC with linear/nonlinear dashed fits.
    valid = crop & np.isfinite(force_aligned)
    x = adc_f[valid]
    y = force_aligned[valid]
    models = fit_models(x, y)
    fig, ax = plt.subplots(figsize=(4.9, 3.7), constrained_layout=True)
    ax.scatter(x, y, s=11, alpha=0.38, color="#4C78A8", edgecolors="none", label="samples")
    bx, by = binned_median(x, y)
    if len(bx):
        ax.plot(bx, by, color="#111111", linestyle="--", linewidth=1.3, label="binned median")
    if "linear" in models:
        xx = np.linspace(float(np.nanmin(x)), float(np.nanmax(x)), 120)
        lin = np.polyval(models["linear"]["coef"], xx)
        quad = np.polyval(models["quadratic"]["coef"], xx)
        ax.plot(xx, lin, color="#E45756", linestyle="--", linewidth=1.1, label=f"linear R2={models['linear']['r2']:.2f}")
        ax.plot(xx, quad, color="#54A24B", linestyle="--", linewidth=1.1, label=f"quadratic R2={models['quadratic']['r2']:.2f}")
    ax.set_xlabel("Filtered raw delta")
    ax.set_ylabel("Force (N)")
    ax.set_title("F-ADC Response")
    ax.grid(True, alpha=0.25)
    ax.legend(frameon=False)
    save_svg(fig, output / "03_force_adc_response.svg")

    # 04a initial-style 2D heatmap with readable annotations.
    peak_i = int(events["adc_peak_i"])
    heat = matrix["delta_stack"][peak_i]
    fig, ax = plt.subplots(figsize=(4.6, 3.8), constrained_layout=True)
    vmax = max(1.0, float(np.nanmax(np.abs(heat))))
    im = ax.imshow(heat, cmap="RdBu_r", vmin=-vmax, vmax=vmax)
    ax.set_title("Peak Heatmap 2D")
    ax.set_xlabel("Column")
    ax.set_ylabel("Row")
    ax.set_xticks(range(8))
    ax.set_yticks(range(8))
    ax.plot(args.target_col, args.target_row, "ko", ms=5, fillstyle="none")
    for r in range(8):
        for c in range(8):
            value = heat[r, c]
            color = "white" if abs(value) > 0.45 * vmax else "black"
            ax.text(
                c,
                r,
                f"{value:.0f}",
                ha="center",
                va="center",
                fontsize=6.0,
                color=color,
            )
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="raw delta")
    save_svg(fig, output / "04a_peak_heatmap_2d_values.svg")

    # 04b 3D heatmap surface.
    fig = plt.figure(figsize=(5.2, 4.2), constrained_layout=True)
    ax = fig.add_subplot(111, projection="3d")
    xx, yy = np.meshgrid(np.arange(8), np.arange(8))
    surf = ax.plot_surface(xx, yy, heat, cmap="turbo", linewidth=0.35, edgecolor="0.30", antialiased=True, alpha=0.94)
    ax.scatter([args.target_col], [args.target_row], [heat[args.target_row, args.target_col]], color="black", s=24)
    ax.set_title("Peak Heatmap 3D")
    ax.set_xlabel("Column")
    ax.set_ylabel("Row")
    ax.set_zlabel("Raw delta")
    ax.set_xticks(range(8))
    ax.set_yticks(range(8))
    for r in range(8):
        for c in range(8):
            ax.text(c, r, heat[r, c], f"{heat[r, c]:.0f}", fontsize=5.2, ha="center")
    fig.colorbar(surf, ax=ax, fraction=0.046, pad=0.04, label="raw delta")
    save_svg(fig, output / "04b_peak_heatmap_3d_values.svg")

    result = {
        "alignment": "contact-onset alignment; ADC contact threshold and force contact threshold are separately detected",
        "events": events,
        "crop_window_s": [crop_start, crop_stop],
        "target": {"row": args.target_row, "col": args.target_col},
        "fit_models": models,
        "diagnosis": {
            "adc_contact_to_peak_s": float(events["adc_peak_s"] - events["adc_contact_s"]),
            "force_contact_to_peak_s": float(events["force_peak_s"] - events["force_contact_s"]),
            "interpretation": "ADC and force have different contact-to-peak durations; expect nonlinearity/slip/local contact effects, not a pure time shift.",
        },
        "outputs": [
            "01_raw_data_full.svg",
            "02_filtered_force_overlay.svg",
            "03_force_adc_response.svg",
            "04a_peak_heatmap_2d_values.svg",
            "04b_peak_heatmap_3d_values.svg",
        ],
    }
    (output / "R4C3_run1_v2_results.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved v2 SVGs -> {output}")
    print(json.dumps(result["diagnosis"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
