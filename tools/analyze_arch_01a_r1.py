#!/usr/bin/env python3
"""Analyze ORDER-ARCH-01A-R1 single-condition captures and emit report SVGs."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np


CONDITION_ORDER = ["100k", "47k", "22k", "10k", "10k_REPEAT", "22k_REPEAT", "47k_REPEAT", "100k_REPEAT"]
FIRST_ORDER = ["100k", "47k", "22k", "10k"]
REPEAT_PAIRS = [("100k", "100k_REPEAT"), ("47k", "47k_REPEAT"), ("22k", "22k_REPEAT"), ("10k", "10k_REPEAT")]
PHASES = ["OPEN_CHECK_PRE", "RTEST_CAPTURE", "OPEN_CHECK_POST"]
CHANNELS = [f"c{i}_raw" for i in range(8)]


def setup_plot_style() -> None:
    mpl.rcParams.update(
        {
            "figure.figsize": (7.2, 4.6),
            "figure.dpi": 140,
            "savefig.dpi": 300,
            "font.family": "DejaVu Sans",
            "font.size": 9.5,
            "axes.titlesize": 11,
            "axes.labelsize": 9.5,
            "axes.linewidth": 0.8,
            "axes.edgecolor": "#30343b",
            "axes.labelcolor": "#20242a",
            "xtick.color": "#20242a",
            "ytick.color": "#20242a",
            "xtick.major.size": 3.5,
            "ytick.major.size": 3.5,
            "grid.color": "#d8dde6",
            "grid.linewidth": 0.6,
            "grid.alpha": 0.8,
            "legend.frameon": False,
            "svg.fonttype": "none",
        }
    )


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def raw_to_voltage(raw: float, vdda: float) -> float:
    return raw * vdda / 65535.0


def stats(values: np.ndarray, vdda: float) -> dict[str, float | int]:
    mean_raw = float(np.mean(values))
    std_raw = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
    return {
        "sample_count": int(len(values)),
        "mean_raw": mean_raw,
        "std_raw": std_raw,
        "mean_v": raw_to_voltage(mean_raw, vdda),
        "std_v": raw_to_voltage(std_raw, vdda),
        "min_raw": int(np.min(values)),
        "max_raw": int(np.max(values)),
        "p2p_raw": int(np.max(values) - np.min(values)),
    }


def load_phase(dataset_dir: Path, condition: str, phase: str) -> list[dict[str, str]]:
    path = dataset_dir / f"{condition}__{phase}.csv"
    return read_csv(path) if path.exists() else []


def measured_rows(dataset_dir: Path, metadata: dict) -> list[dict[str, object]]:
    vdda = float(metadata.get("vdda_v", 3.29))
    vref = float(metadata.get("vref_v", 1.03))
    rf = float(metadata.get("rf_ohm", 10170.0))
    open_threshold = float(metadata.get("open_threshold_v", 0.030))
    stored_results = {}
    results_path = dataset_dir / "condition_results.csv"
    if results_path.exists():
        stored_results = {row["condition"]: row for row in read_csv(results_path)}

    summary: list[dict[str, object]] = []
    for condition in CONDITION_ORDER:
        if not (dataset_dir / f"{condition}__RTEST_CAPTURE.csv").exists():
            continue
        condition_meta = metadata.get("conditions", {}).get(condition, {})
        result_row = stored_results.get(condition, {})
        actual_r = float(condition_meta.get("actual_r_ohm") or result_row.get("actual_r_ohm") or "nan")

        phase_stats = {}
        for phase in PHASES:
            rows = load_phase(dataset_dir, condition, phase)
            phase_stats[phase] = stats(np.array([float(row["c0_raw"]) for row in rows], dtype=float), vdda) if rows else {"sample_count": 0}

        expected_vout = vref * (1.0 + rf / actual_r)
        rtest_mean = float(phase_stats["RTEST_CAPTURE"]["mean_v"])
        error_v = rtest_mean - expected_vout
        open_post_delta = float(phase_stats["OPEN_CHECK_POST"]["mean_v"]) - float(phase_stats["OPEN_CHECK_PRE"]["mean_v"])
        validity = str(condition_meta.get("validity_flag") or result_row.get("validity_flag") or "")
        if not validity:
            validity = "VALID" if abs(open_post_delta) <= open_threshold else "INVALID_CONTACT_STATE"

        summary.append(
            {
                "condition": condition,
                "base_condition": condition.replace("_REPEAT", ""),
                "is_repeat": "YES" if "_REPEAT" in condition else "NO",
                "actual_r_ohm": actual_r,
                "validity_flag": validity,
                "invalid_reason": condition_meta.get("invalid_reason") or result_row.get("invalid_reason") or "",
                "open_pre_mean_v": phase_stats["OPEN_CHECK_PRE"]["mean_v"],
                "open_pre_std_v": phase_stats["OPEN_CHECK_PRE"]["std_v"],
                "rtest_mean_v": rtest_mean,
                "rtest_std_v": phase_stats["RTEST_CAPTURE"]["std_v"],
                "open_post_mean_v": phase_stats["OPEN_CHECK_POST"]["mean_v"],
                "open_post_std_v": phase_stats["OPEN_CHECK_POST"]["std_v"],
                "open_post_delta_vs_pre_v": open_post_delta,
                "vexpected_v": expected_vout,
                "delta_v_mean": rtest_mean - vref,
                "error_v": error_v,
                "error_percent": 100.0 * error_v / expected_vout if expected_vout else math.nan,
                "pin2_manual_v": condition_meta.get("pin2_manual_v") or result_row.get("pin2_manual_v") or "",
            }
        )
    return summary


def compute_control_summary(dataset_dir: Path, metadata: dict) -> list[dict[str, object]]:
    vdda = float(metadata.get("vdda_v", 3.29))
    rows_out: list[dict[str, object]] = []
    for condition in CONDITION_ORDER:
        rtest_rows = load_phase(dataset_dir, condition, "RTEST_CAPTURE")
        if not rtest_rows:
            continue
        for channel in range(1, 8):
            raw = np.array([float(row[f"c{channel}_raw"]) for row in rtest_rows], dtype=float)
            item = stats(raw, vdda)
            rows_out.append(
                {
                    "condition": condition,
                    "channel": f"COL{channel}",
                    "mean_raw": item["mean_raw"],
                    "std_raw": item["std_raw"],
                    "mean_v": item["mean_v"],
                    "std_v": item["std_v"],
                    "p2p_raw": item["p2p_raw"],
                }
            )
    return rows_out


def fit_and_classify(summary: list[dict[str, object]], metadata: dict) -> dict[str, object]:
    valid = {str(row["condition"]): row for row in summary if row["validity_flag"] == "VALID"}
    primary = [valid[name] for name in FIRST_ORDER if name in valid]
    x = np.array([1.0 / float(row["actual_r_ohm"]) for row in primary], dtype=float)
    y = np.array([float(row["delta_v_mean"]) for row in primary], dtype=float)
    if len(primary) >= 2:
        slope, intercept = np.polyfit(x, y, 1)
        predicted = slope * x + intercept
        ss_res = float(np.sum((y - predicted) ** 2))
        ss_tot = float(np.sum((y - float(np.mean(y))) ** 2))
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else math.nan
    else:
        slope = intercept = r2 = math.nan
    vref = float(metadata.get("vref_v", 1.03))
    rf_eff = slope / vref if not math.isnan(slope) and vref else math.nan

    repeatability = {}
    for first, repeat in REPEAT_PAIRS:
        if first in valid and repeat in valid:
            a = float(valid[first]["rtest_mean_v"])
            b = float(valid[repeat]["rtest_mean_v"])
            repeatability[first] = {
                "first_v": a,
                "repeat_v": b,
                "diff_v": b - a,
                "percent_diff_vs_first": 100.0 * (b - a) / a if abs(a) > 1e-12 else math.nan,
            }

    reasons = []
    all_expected = set(CONDITION_ORDER).issubset({str(row["condition"]) for row in summary})
    all_valid = all(str(row["validity_flag"]) == "VALID" for row in summary) and all_expected
    if not all_valid:
        reasons.append("Not all expected conditions are valid.")
    if len(primary) == 4:
        vouts = [float(row["rtest_mean_v"]) for row in primary]
        # ORDER is 100k -> 47k -> 22k -> 10k; Vout should increase.
        if any(vouts[i + 1] <= vouts[i] for i in range(len(vouts) - 1)):
            reasons.append("Primary points are not monotonic from 100k to 10k.")
    else:
        reasons.append("Missing valid primary points for monotonic check.")
    if len(repeatability) != 4:
        reasons.append("Missing valid repeat pairs.")
    for name, item in repeatability.items():
        if abs(float(item["diff_v"])) > 0.030:
            reasons.append(f"{name} repeat differs by more than 30 mV.")

    return {
        "status": "PASS" if not reasons else "FAIL",
        "fail_reasons": reasons,
        "slope": slope,
        "intercept": intercept,
        "r_squared": r2,
        "rf_eff_ohm": rf_eff,
        "repeatability": repeatability,
    }


def save_svg(fig: plt.Figure, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, format="svg", bbox_inches="tight")
    plt.close(fig)


def make_plots(dataset_dir: Path, summary: list[dict[str, object]], control: list[dict[str, object]], fit: dict, metadata: dict) -> None:
    setup_plot_style()
    plots = dataset_dir / "plots"
    plots.mkdir(parents=True, exist_ok=True)
    by = {str(row["condition"]): row for row in summary}
    valid_first = [by[name] for name in FIRST_ORDER if name in by and by[name]["validity_flag"] == "VALID"]
    vref = float(metadata.get("vref_v", 1.03))
    rf = float(metadata.get("rf_ohm", 10170.0))
    blue = "#1f77b4"
    red = "#b23b3b"
    gray = "#68707a"
    green = "#2f7d4f"

    if valid_first:
        r = np.array([float(row["actual_r_ohm"]) for row in valid_first])
        inv_r = 1.0 / r
        measured = np.array([float(row["delta_v_mean"]) for row in valid_first])
        theory = vref * rf / r
        fig, ax = plt.subplots(figsize=(7.0, 4.4))
        ax.plot(inv_r, theory, color=gray, linewidth=1.5, linestyle="--", label="Expected")
        ax.scatter(inv_r, measured, s=42, color=blue, edgecolor="white", linewidth=0.8, label="Measured")
        if not math.isnan(float(fit.get("slope", math.nan))):
            xfit = np.linspace(float(inv_r.min()), float(inv_r.max()), 100)
            ax.plot(xfit, float(fit["slope"]) * xfit + float(fit["intercept"]), color=red, linewidth=1.6, label="Linear fit")
        for row, xval, yval in zip(valid_first, inv_r, measured):
            ax.annotate(str(row["condition"]), (xval, yval), xytext=(4, 5), textcoords="offset points", fontsize=8)
        ax.set_xlabel("Conductance, 1/R (1/ohm)")
        ax.set_ylabel("COL0 delta V (V)")
        ax.set_title(f"Direct TIA transfer, R2={float(fit.get('r_squared', math.nan)):.6f}")
        ax.grid(True)
        ax.legend(loc="best")
        save_svg(fig, plots / "01_r1_deltaV_vs_inverseR.svg")

        fig, ax = plt.subplots(figsize=(7.0, 4.4))
        residual = measured - theory
        ax.axhline(0, color=gray, linewidth=1.0)
        ax.plot(r, residual, marker="o", color=red, linewidth=1.4)
        ax.set_xscale("log")
        ax.invert_xaxis()
        ax.set_xlabel("Rtest (ohm, log scale)")
        ax.set_ylabel("Measured - expected Vout (V)")
        ax.set_title("Residual by resistance")
        ax.grid(True, which="both")
        save_svg(fig, plots / "04_r1_residual_vs_R.svg")

    fig, ax = plt.subplots(figsize=(8.2, 4.6))
    x = np.arange(len(summary))
    labels = [str(row["condition"]) for row in summary]
    pre = np.array([float(row["open_pre_mean_v"]) for row in summary])
    post = np.array([float(row["open_post_mean_v"]) for row in summary])
    ref = float(metadata.get("open_reference_v", 1.035))
    thresh = float(metadata.get("open_threshold_v", 0.030))
    ax.axhspan(ref - thresh, ref + thresh, color="#e9f2fb", alpha=0.9, label="Open window")
    ax.axhline(ref, color=gray, linewidth=1.0, linestyle="--", label="Open reference")
    ax.plot(x, pre, marker="o", color=blue, linewidth=1.3, label="OPEN_PRE")
    ax.plot(x, post, marker="s", color=green, linewidth=1.3, label="OPEN_POST")
    ax.set_xticks(x, labels, rotation=35, ha="right")
    ax.set_ylabel("COL0 Vout (V)")
    ax.set_title("Open-state recovery checks")
    ax.grid(True, axis="y")
    ax.legend(loc="best", ncol=3)
    save_svg(fig, plots / "02_r1_open_recovery.svg")

    fig, ax = plt.subplots(figsize=(7.0, 4.4))
    pair_labels = []
    first_values = []
    repeat_values = []
    for first, repeat in REPEAT_PAIRS:
        if first in by and repeat in by:
            pair_labels.append(first)
            first_values.append(float(by[first]["rtest_mean_v"]))
            repeat_values.append(float(by[repeat]["rtest_mean_v"]))
    xpos = np.arange(len(pair_labels))
    width = 0.34
    ax.bar(xpos - width / 2, first_values, width=width, color=blue, label="First")
    ax.bar(xpos + width / 2, repeat_values, width=width, color=green, label="Repeat")
    ax.set_xticks(xpos, pair_labels)
    ax.set_ylabel("COL0 Vout (V)")
    ax.set_title("Repeatability of key resistors")
    ax.grid(True, axis="y")
    ax.legend(loc="best")
    save_svg(fig, plots / "03_r1_repeatability.svg")

    fig, ax = plt.subplots(figsize=(9.0, 4.6))
    cursor = 0
    colors = {"OPEN_CHECK_PRE": "#7b8794", "RTEST_CAPTURE": blue, "OPEN_CHECK_POST": "#2f7d4f"}
    for condition in CONDITION_ORDER:
        if condition not in by:
            continue
        for phase in PHASES:
            rows = load_phase(dataset_dir, condition, phase)
            if not rows:
                continue
            raw = np.array([float(row["c0_raw"]) for row in rows], dtype=float)
            y = raw_to_voltage(raw, float(metadata.get("vdda_v", 3.29)))
            xvals = np.arange(len(y)) + cursor
            ax.plot(xvals, y, color=colors[phase], linewidth=0.55, alpha=0.85)
            cursor += len(y)
        ax.axvline(cursor, color="#e0e4ea", linewidth=0.6)
    ax.set_xlabel("Sample index, concatenated by condition")
    ax.set_ylabel("COL0 Vout (V)")
    ax.set_title("Protocol trace: OPEN_PRE, RTEST, OPEN_POST")
    ax.grid(True, axis="y")
    handles = [plt.Line2D([0], [0], color=colors[p], lw=1.6, label=p.replace("_", " ")) for p in PHASES]
    ax.legend(handles=handles, loc="best", ncol=3)
    save_svg(fig, plots / "05_r1_col0_protocol_trace.svg")

    fig, ax = plt.subplots(figsize=(7.0, 4.4))
    channels = [f"COL{i}" for i in range(1, 8)]
    stds = []
    for channel in channels:
        values = [float(row["std_v"]) for row in control if row["channel"] == channel]
        stds.append(float(np.mean(values)) if values else 0.0)
    ax.bar(channels, stds, color="#5b6776")
    ax.set_ylabel("Mean standard deviation (V)")
    ax.set_title("Control-channel noise during RTEST")
    ax.grid(True, axis="y")
    save_svg(fig, plots / "06_r1_control_channel_std.svg")


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze ORDER-ARCH-01A-R1 dataset.")
    parser.add_argument("dataset_dir", type=Path)
    args = parser.parse_args()
    dataset_dir = args.dataset_dir.resolve()
    metadata = json.loads((dataset_dir / "metadata.json").read_text(encoding="utf-8-sig"))
    summary = measured_rows(dataset_dir, metadata)
    control = compute_control_summary(dataset_dir, metadata)
    fit = fit_and_classify(summary, metadata)

    write_csv(dataset_dir / "summary.csv", summary)
    write_csv(dataset_dir / "control_channels_summary.csv", control)
    (dataset_dir / "fit_results.json").write_text(json.dumps(fit, indent=2), encoding="utf-8")
    make_plots(dataset_dir, summary, control, fit, metadata)

    print(f"Dataset: {dataset_dir}")
    print(f"STATUS: {fit['status']}")
    print(f"R2: {float(fit.get('r_squared', math.nan)):.6f}")
    if fit["fail_reasons"]:
        print("Reasons:")
        for reason in fit["fail_reasons"]:
            print(f"- {reason}")
    return 0 if fit["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
