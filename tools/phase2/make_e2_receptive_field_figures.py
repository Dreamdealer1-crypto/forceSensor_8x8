#!/usr/bin/env python3
"""Generate E2 receptive-field figures from one force-ramp capture."""

from __future__ import annotations

import argparse
import json
import math
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
    "savefig.bbox": "tight",
}


def filter_signal(values: np.ndarray, median_window: int = 7, mean_window: int = 31) -> np.ndarray:
    series = pd.Series(values).interpolate(limit_direction="both")
    median = series.rolling(window=median_window, center=True, min_periods=1).median()
    smooth = median.rolling(window=mean_window, center=True, min_periods=1).mean()
    return smooth.to_numpy(float)


def load_force_first_run(path: Path) -> tuple[np.ndarray, np.ndarray]:
    raw = pd.read_excel(path, sheet_name=0, header=None)
    block = raw.iloc[:, 0:10]
    data = block.iloc[9:]
    force = pd.to_numeric(data.iloc[:, 1], errors="coerce").to_numpy(float)
    time_s = pd.to_numeric(data.iloc[:, 3], errors="coerce").to_numpy(float)
    mask = np.isfinite(time_s) & np.isfinite(force)
    time_s = time_s[mask]
    force = force[mask]
    time_s -= time_s[0]
    return time_s, force


def load_matrix(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    df = pd.read_csv(path)
    time_s = pd.to_numeric(df["elapsed_s"], errors="coerce").to_numpy(float)
    time_s -= np.nanmin(time_s)
    raw_cols = [f"r{r}c{c}_raw" for r in range(8) for c in range(8)]
    stack = df[raw_cols].apply(pd.to_numeric, errors="coerce").to_numpy(float).reshape((-1, 8, 8))
    baseline_n = max(10, min(60, len(stack) // 25))
    baseline = np.nanmedian(stack[:baseline_n], axis=0)
    delta = stack - baseline
    return time_s, stack, delta


def detect_contact_and_align(matrix_t: np.ndarray, delta: np.ndarray, target: tuple[int, int], force_t: np.ndarray, force: np.ndarray) -> np.ndarray:
    trace = filter_signal(delta[:, target[0], target[1]])
    adc_noise = float(np.nanstd(trace[:100]))
    adc_thr = max(300.0, 5.0 * adc_noise)
    adc_contact_i = int(np.flatnonzero(trace > adc_thr)[0])
    force_noise = float(np.nanstd(force[:20]))
    force_thr = max(0.5, float(np.nanmedian(force[:20]) + 5.0 * force_noise))
    force_contact_i = int(np.flatnonzero(force > force_thr)[0])
    shift = float(matrix_t[adc_contact_i] - force_t[force_contact_i])
    force_on_matrix_t = matrix_t - shift
    aligned_force = np.full_like(matrix_t, np.nan, dtype=float)
    mask = (force_on_matrix_t >= force_t[0]) & (force_on_matrix_t <= force_t[-1])
    aligned_force[mask] = np.interp(force_on_matrix_t[mask], force_t, force)
    return aligned_force


def response_at_force(delta: np.ndarray, aligned_force: np.ndarray, target_force: float, window_n: float = 0.5) -> np.ndarray:
    mask = np.isfinite(aligned_force) & (np.abs(aligned_force - target_force) <= window_n)
    if not np.any(mask):
        idx = int(np.nanargmin(np.abs(aligned_force - target_force)))
        return delta[idx]
    return np.nanmedian(delta[mask], axis=0)


def normalize_map(matrix: np.ndarray) -> np.ndarray:
    peak = float(np.nanmax(np.abs(matrix)))
    return matrix / peak if peak > 0 else matrix


def line_profiles(matrix: np.ndarray, target: tuple[int, int]) -> dict[str, np.ndarray]:
    r, c = target
    return {
        "row": matrix[r, :],
        "col": matrix[:, c],
        "diag": np.array([matrix[i, j] for i, j in zip(range(8), range(c - r, c - r + 8), strict=False) if 0 <= j < 8]),
    }


def polar_radius(norm: np.ndarray, target: tuple[int, int], threshold: float = 0.10) -> tuple[np.ndarray, np.ndarray]:
    angles = np.linspace(0, 2 * np.pi, 17)[:-1]
    radii = []
    tr, tc = target
    for theta in angles:
        radius = 0.0
        for rr in np.linspace(0, 5, 101):
            y = tr + rr * math.sin(theta)
            x = tc + rr * math.cos(theta)
            iy, ix = int(round(y)), int(round(x))
            if not (0 <= iy < 8 and 0 <= ix < 8):
                break
            if norm[iy, ix] >= threshold:
                radius = rr
        radii.append(radius)
    return angles, np.asarray(radii)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-xls", default="data/phase2/force_ramp/R3C3_40N/20260827-01.xls")
    parser.add_argument("--matrix-csv", default="data/phase2/force_ramp/R3C3_40N/20260827_002209_R3C3_ramp_0p2N_s/force_ramp.csv")
    parser.add_argument("--output-dir", default="data/phase2/force_ramp/R3C3_40N/e2_receptive_field_run1")
    parser.add_argument("--target-row", type=int, default=4)
    parser.add_argument("--target-col", type=int, default=3)
    parser.add_argument("--forces", default="5,15,25,35")
    parser.add_argument("--indenter-diameter-mm", type=float, default=4.0)
    args = parser.parse_args()
    plt.rcParams.update(STYLE)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    target = (args.target_row, args.target_col)
    force_levels = [float(x) for x in args.forces.split(",")]

    ft, force = load_force_first_run(Path(args.force_xls))
    mt, _, delta = load_matrix(Path(args.matrix_csv))
    aligned_force = detect_contact_and_align(mt, delta, target, ft, force)
    maps = [response_at_force(delta, aligned_force, level) for level in force_levels]
    peak_map = maps[-1]
    norm_peak = normalize_map(peak_map)
    eta_angles, eta_r = polar_radius(norm_peak, target)
    eta = float(np.nanmean(eta_r))

    # 1 line profiles
    x = np.arange(8)
    fig, axes = plt.subplots(1, 3, figsize=(9.0, 3.0), constrained_layout=True)
    titles = ["row scan", "column scan", "diagonal scan"]
    keys = ["row", "col", "diag"]
    for ax, key, title in zip(axes, keys, titles, strict=True):
        for level, matrix in zip(force_levels, maps, strict=True):
            prof = line_profiles(matrix, target)[key]
            ax.plot(np.arange(len(prof)), prof, marker="o", linewidth=1.0, label=f"{level:g} N")
        ax.set_title(title)
        ax.set_xlabel("Taxel index")
        ax.set_ylabel("Raw delta")
        ax.grid(True, alpha=0.25)
    axes[0].legend(frameon=False)
    fig.suptitle("Line Profiles", fontsize=11)
    fig.savefig(output / "E2_line_profiles.png", dpi=300)
    plt.close(fig)

    # 2 RF map with contours
    fig, ax = plt.subplots(figsize=(4.6, 3.9), constrained_layout=True)
    im = ax.imshow(norm_peak, cmap="turbo", interpolation="bicubic", vmin=0, vmax=max(1.0, np.nanmax(norm_peak)))
    levels = [0.1, 0.25, 0.5, 0.75]
    cs = ax.contour(norm_peak, levels=levels, colors="white", linewidths=0.9)
    ax.clabel(cs, inline=True, fontsize=7, fmt="%.2f")
    ax.plot(target[1], target[0], "wo", ms=7, mfc="none", mew=1.4)
    ax.set_title("2D Receptive Field")
    ax.set_xlabel("Column")
    ax.set_ylabel("Row")
    ax.set_xticks(range(8))
    ax.set_yticks(range(8))
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="Normalized response")
    fig.savefig(output / "E2_rf_2d_map.png", dpi=300)
    plt.close(fig)

    # 3 polar
    fig = plt.figure(figsize=(4.0, 3.8), constrained_layout=True)
    ax = fig.add_subplot(111, projection="polar")
    closed_angles = np.r_[eta_angles, eta_angles[0]]
    closed_r = np.r_[eta_r, eta_r[0]]
    ax.plot(closed_angles, closed_r, color="#4C78A8", linewidth=1.5)
    ax.fill(closed_angles, closed_r, color="#4C78A8", alpha=0.20)
    ax.set_title("RF Polar Radius")
    fig.savefig(output / "E2_rf_polar.png", dpi=300)
    plt.close(fig)

    # 4 neighbor response
    tr, tc = target
    neighbors = [(tr - 1, tc - 1), (tr - 1, tc), (tr - 1, tc + 1), (tr, tc - 1), (tr, tc + 1), (tr + 1, tc - 1), (tr + 1, tc), (tr + 1, tc + 1)]
    vals = [norm_peak[r, c] if 0 <= r < 8 and 0 <= c < 8 else np.nan for r, c in neighbors]
    labels = [f"R{r}C{c}" for r, c in neighbors]
    fig, ax = plt.subplots(figsize=(5.0, 3.2), constrained_layout=True)
    ax.bar(labels, vals, color="#4C78A8", edgecolor="black", linewidth=0.5)
    ax.axhline(0.1, color="#E45756", linestyle="--", linewidth=1.0, label="10% threshold")
    ax.set_title("Neighbor Response")
    ax.set_ylabel("Neighbor / peak")
    ax.tick_params(axis="x", rotation=45)
    ax.legend(frameon=False)
    fig.savefig(output / "E2_neighbor_response.png", dpi=300)
    plt.close(fig)

    # 5 overlap diagram
    fig, ax = plt.subplots(figsize=(4.4, 4.0), constrained_layout=True)
    ax.set_aspect("equal")
    ax.set_xlim(-0.5, 7.5)
    ax.set_ylim(7.5, -0.5)
    for r in range(8):
        for c in range(8):
            ax.plot(c, r, "o", color="0.65", ms=4)
    circle = plt.Circle((target[1], target[0]), eta, fill=False, color="#E45756", linewidth=2.0)
    indenter_radius_taxel = args.indenter_diameter_mm / 10.0 / 2.0
    indenter = plt.Circle((target[1], target[0]), indenter_radius_taxel, fill=False, color="#111111", linestyle="--", linewidth=1.2)
    ax.add_patch(circle)
    ax.add_patch(indenter)
    ax.plot(target[1], target[0], "o", color="#E45756", ms=7)
    ax.set_title(f"RF Overlap, eta={eta:.2f}")
    ax.set_xlabel("Column")
    ax.set_ylabel("Row")
    ax.set_xticks(range(8))
    ax.set_yticks(range(8))
    fig.savefig(output / "E2_overlap_diagram.png", dpi=300)
    plt.close(fig)

    # 6 shift invariance placeholder with current T0 and required missing T1/T2.
    fig, axes = plt.subplots(1, 3, figsize=(8.5, 3.0), constrained_layout=True)
    for ax, title in zip(axes, ["T0 measured", "T1 pending", "T2 pending"], strict=True):
        if title.startswith("T0"):
            im = ax.imshow(norm_peak, cmap="turbo", vmin=0, vmax=1)
            ax.plot(target[1], target[0], "wo", ms=7, mfc="none", mew=1.4)
        else:
            ax.imshow(np.zeros((8, 8)), cmap="Greys", vmin=0, vmax=1)
            ax.text(3.5, 3.5, "need shifted\nposition data", ha="center", va="center", fontsize=10)
        ax.set_title(title)
        ax.set_xticks(range(8))
        ax.set_yticks(range(8))
    fig.colorbar(im, ax=axes, fraction=0.046, pad=0.04, label="Normalized response")
    fig.savefig(output / "E2_shift_invariance.png", dpi=300)
    plt.close(fig)

    result = {
        "target": {"row": target[0], "col": target[1]},
        "force_levels_N": force_levels,
        "indenter_diameter_mm": args.indenter_diameter_mm,
        "eta_taxel_pitch_units": eta,
        "note": "Shift invariance requires additional T1/T2 shifted-position captures; current figure marks them pending.",
    }
    (output / "E2_results.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved E2 figures -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
