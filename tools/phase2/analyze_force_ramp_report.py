#!/usr/bin/env python3
"""Analyze compression-instrument force logs against 8x8 ramp captures."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


IEEE_STYLE = {
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
    time_s: np.ndarray
    force_n: np.ndarray
    displacement_mm: np.ndarray
    start_epoch_s: float | None = None


@dataclass
class MatrixRun:
    path: Path
    label: str
    time_s: np.ndarray
    target_raw: np.ndarray
    target_delta: np.ndarray
    final_delta_matrix: np.ndarray
    peak_delta_matrix: np.ndarray
    frame_rate_hz: float
    host_time_s: np.ndarray


def save_svg(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, format="svg")
    plt.close(fig)


def _numeric(values: pd.Series) -> np.ndarray:
    return pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)


def load_force_runs(path: Path) -> list[ForceRun]:
    raw = pd.read_excel(path, sheet_name=0, header=None)
    runs: list[ForceRun] = []
    for start_col in range(0, raw.shape[1], 10):
        block = raw.iloc[:, start_col : start_col + 10]
        if block.shape[1] < 4:
            continue
        title = str(block.iloc[0, 0])
        if "测试编号" not in title:
            continue
        headers = [str(x).strip() for x in block.iloc[8].tolist()]
        try:
            force_col = headers.index("N")
            displacement_col = headers.index("mm")
            time_col = headers.index("sec")
        except ValueError:
            force_col, displacement_col, time_col = 1, 2, 3
        data = block.iloc[9:].copy()
        time_s = _numeric(data.iloc[:, time_col])
        force_n = _numeric(data.iloc[:, force_col])
        displacement_mm = _numeric(data.iloc[:, displacement_col])
        mask = np.isfinite(time_s) & np.isfinite(force_n)
        if np.sum(mask) < 5:
            continue
        match = re.search(r"测试编号:([^ ]+)\s+(.*)$", title)
        label = match.group(1) if match else f"run{len(runs)+1}"
        start_text = match.group(2) if match else ""
        start_epoch = None
        try:
            start_epoch = datetime.strptime(start_text, "%Y-%m-%d %H:%M:%S.%f").timestamp()
        except ValueError:
            try:
                start_epoch = datetime.strptime(start_text, "%Y-%m-%d %H:%M:%S").timestamp()
            except ValueError:
                start_epoch = None
        runs.append(ForceRun(label, start_text, time_s[mask], force_n[mask], displacement_mm[mask], start_epoch))
    if not runs:
        raise RuntimeError(f"no force runs parsed from {path}")
    return runs


def load_matrix_run(path: Path, target: tuple[int, int]) -> MatrixRun:
    df = pd.read_csv(path)
    tr, tc = target
    target_key = f"r{tr}c{tc}_raw"
    time_s = pd.to_numeric(df["elapsed_s"], errors="coerce").to_numpy(dtype=float)
    time_s = time_s - np.nanmin(time_s)
    target_raw = pd.to_numeric(df[target_key], errors="coerce").to_numpy(dtype=float)
    host_time_s = pd.to_numeric(df["host_time_s"], errors="coerce").to_numpy(dtype=float) if "host_time_s" in df else time_s.copy()
    baseline_n = max(5, min(40, len(target_raw) // 20))
    baseline = float(np.nanmedian(target_raw[:baseline_n]))
    target_delta = target_raw - baseline

    raw_cols = [f"r{r}c{c}_raw" for r in range(8) for c in range(8)]
    raw_stack = df[raw_cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float).reshape((-1, 8, 8))
    baseline_matrix = np.nanmedian(raw_stack[:baseline_n], axis=0)
    delta_stack = raw_stack - baseline_matrix
    final_delta_matrix = np.nanmedian(delta_stack[-baseline_n:], axis=0)
    peak_index = int(np.nanargmax(np.abs(target_delta)))
    peak_delta_matrix = delta_stack[peak_index]
    frame_rate = (len(time_s) - 1) / (time_s[-1] - time_s[0]) if len(time_s) > 1 and time_s[-1] > time_s[0] else 0.0
    return MatrixRun(path, path.parent.name, time_s, target_raw, target_delta, final_delta_matrix, peak_delta_matrix, frame_rate, host_time_s)


def align_force_to_matrix(force: ForceRun, matrix: MatrixRun) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    force_time = force.time_s - force.time_s[0]
    if force.start_epoch_s is not None and np.all(np.isfinite(matrix.host_time_s)):
        matrix_force_time = matrix.host_time_s - force.start_epoch_s
    else:
        matrix_force_time = matrix.time_s - matrix.time_s[0]
    mask = (matrix_force_time >= force_time[0]) & (matrix_force_time <= force_time[-1])
    t = matrix_force_time[mask]
    force_interp = np.interp(t, force_time, force.force_n)
    adc = matrix.target_delta[mask]
    return t, force_interp, adc


def fit_linear(force_n: np.ndarray, adc_delta: np.ndarray) -> dict[str, float]:
    mask = np.isfinite(force_n) & np.isfinite(adc_delta)
    mask &= force_n >= max(0.2, np.nanpercentile(force_n, 5))
    if np.sum(mask) < 3:
        return {"slope_raw_per_N": float("nan"), "intercept_raw": float("nan"), "r2": float("nan")}
    x = force_n[mask]
    y = adc_delta[mask]
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return {"slope_raw_per_N": float(slope), "intercept_raw": float(intercept), "r2": float(r2)}


def plot_force_time(output: Path, pairs: list[tuple[ForceRun, MatrixRun]]) -> None:
    fig, ax1 = plt.subplots(figsize=(6.8, 3.2), constrained_layout=True)
    ax2 = ax1.twinx()
    colors = ["#1f77b4", "#d62728"]
    for idx, (force, matrix) in enumerate(pairs):
        t, f, adc = align_force_to_matrix(force, matrix)
        color = colors[idx % len(colors)]
        ax1.plot(t, f, color=color, linewidth=1.2, label=f"{force.label} force")
        ax2.plot(t, adc, color=color, linestyle="--", linewidth=1.0, label=f"{force.label} ADC")
    ax1.set_xlabel("Aligned time (s)")
    ax1.set_ylabel("Force (N)")
    ax2.set_ylabel("Target taxel raw delta")
    ax1.set_title("Force ramp and target taxel response")
    lines = ax1.get_lines() + ax2.get_lines()
    ax1.legend(lines, [line.get_label() for line in lines], frameon=False, loc="best")
    ax1.grid(True, alpha=0.25)
    save_svg(fig, output / "force_adc_time_overlay.svg")


def plot_force_adc(output: Path, pairs: list[tuple[ForceRun, MatrixRun]], fits: list[dict[str, float]]) -> None:
    fig, ax = plt.subplots(figsize=(4.6, 3.4), constrained_layout=True)
    colors = ["#1f77b4", "#d62728"]
    for idx, ((force, matrix), fit) in enumerate(zip(pairs, fits, strict=True)):
        _, f, adc = align_force_to_matrix(force, matrix)
        color = colors[idx % len(colors)]
        ax.scatter(f, adc, s=10, alpha=0.45, color=color, edgecolors="none", label=f"{force.label} samples")
        if np.isfinite(fit["slope_raw_per_N"]):
            xx = np.linspace(np.nanmin(f), np.nanmax(f), 100)
            yy = fit["slope_raw_per_N"] * xx + fit["intercept_raw"]
            ax.plot(xx, yy, color=color, linewidth=1.5, label=f"{force.label} fit R2={fit['r2']:.3f}")
    ax.set_xlabel("Force (N)")
    ax.set_ylabel("Target taxel raw delta")
    ax.set_title("Force-ADC response curve")
    ax.grid(True, alpha=0.25)
    ax.legend(frameon=False)
    save_svg(fig, output / "force_adc_response_curve.svg")


def plot_heatmaps(output: Path, matrix_runs: list[MatrixRun], target: tuple[int, int]) -> None:
    fig, axes = plt.subplots(1, len(matrix_runs), figsize=(3.2 * len(matrix_runs), 3.2), constrained_layout=True)
    if len(matrix_runs) == 1:
        axes = [axes]
    vmax = max(float(np.nanmax(np.abs(run.peak_delta_matrix))) for run in matrix_runs)
    vmax = max(vmax, 1.0)
    for ax, run in zip(axes, matrix_runs, strict=True):
        im = ax.imshow(run.peak_delta_matrix, cmap="RdBu_r", vmin=-vmax, vmax=vmax)
        ax.plot(target[1], target[0], "ko", ms=4, fillstyle="none")
        ax.set_title(f"{run.label}\npeak response")
        ax.set_xlabel("Column")
        ax.set_ylabel("Row")
        ax.set_xticks(range(8))
        ax.set_yticks(range(8))
    fig.colorbar(im, ax=axes, fraction=0.046, pad=0.04, label="raw delta")
    save_svg(fig, output / "matrix_peak_heatmaps.svg")


def plot_summary(output: Path, pairs: list[tuple[ForceRun, MatrixRun]], fits: list[dict[str, float]], target: tuple[int, int]) -> None:
    fig, ax = plt.subplots(figsize=(9.6, 5.4), constrained_layout=True)
    ax.axis("off")
    lines = [
        "PHASE 2.0 Force-ADC Ramp Summary",
        f"Target taxel: R{target[0]}C{target[1]}",
        "Alignment: relative time zero of matrix capture and compression log; force values from instrument log.",
        "",
        "Run                         Max Force(N)  Matrix Frames  Matrix Hz  Raw/N slope  R2",
    ]
    for (force, matrix), fit in zip(pairs, fits, strict=True):
        lines.append(
            f"{force.label:<28} {np.nanmax(force.force_n):>10.3f}  {len(matrix.time_s):>13d}  "
            f"{matrix.frame_rate_hz:>8.2f}  {fit['slope_raw_per_N']:>11.2f}  {fit['r2']:>5.3f}"
        )
    ax.text(0.04, 0.94, "\n".join(lines), va="top", family="monospace", fontsize=11)
    save_svg(fig, output / "force_ramp_summary.svg")


def analyze(args: argparse.Namespace) -> int:
    plt.rcParams.update(IEEE_STYLE)
    root = Path(args.dataset_dir).resolve()
    force_path = Path(args.force_xls).resolve()
    output = Path(args.output_dir).resolve() if args.output_dir else root / "analysis_force_ramp"
    output.mkdir(parents=True, exist_ok=True)
    target = (args.grid_row, args.grid_col)

    force_runs = load_force_runs(force_path)
    matrix_paths = sorted(root.glob("*/force_ramp.csv"))
    matrix_runs = [load_matrix_run(path, target) for path in matrix_paths]
    if len(matrix_runs) < 1:
        raise RuntimeError(f"no matrix force_ramp.csv found under {root}")
    pair_count = min(len(force_runs), len(matrix_runs))
    pairs = list(zip(force_runs[:pair_count], matrix_runs[:pair_count], strict=False))
    fits = [fit_linear(*align_force_to_matrix(force, matrix)[1:]) for force, matrix in pairs]

    plot_force_time(output, pairs)
    plot_force_adc(output, pairs, fits)
    plot_heatmaps(output, [matrix for _, matrix in pairs], target)
    plot_summary(output, pairs, fits, target)

    results = {
        "force_xls": str(force_path),
        "dataset_dir": str(root),
        "target": {"row": args.grid_row, "col": args.grid_col},
        "runs": [
            {
                "force_label": force.label,
                "force_start_text": force.start_text,
                "matrix_csv": str(matrix.path),
                "max_force_N": float(np.nanmax(force.force_n)),
                "matrix_frames": int(len(matrix.time_s)),
                "matrix_frame_rate_hz": float(matrix.frame_rate_hz),
                **fit,
            }
            for (force, matrix), fit in zip(pairs, fits, strict=True)
        ],
        "outputs": [
            "force_adc_time_overlay.svg",
            "force_adc_response_curve.svg",
            "matrix_peak_heatmaps.svg",
            "force_ramp_summary.svg",
        ],
    }
    (output / "force_ramp_results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Parsed {len(force_runs)} force runs and {len(matrix_runs)} matrix runs; paired {pair_count}.")
    print(f"Saved report SVGs -> {output}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-xls", required=True)
    parser.add_argument("--dataset-dir", required=True)
    parser.add_argument("--output-dir")
    parser.add_argument("--grid-row", type=int, default=3)
    parser.add_argument("--grid-col", type=int, default=3)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(analyze(parse_args()))
