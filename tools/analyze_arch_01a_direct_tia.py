#!/usr/bin/env python3
"""Analyze ORDER-ARCH-01A direct TIA raw captures."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np


NON_OPEN_PRIMARY = ["1p5M", "470k", "220k", "100k", "68k", "47k", "22k", "10k"]
REPEAT_PAIRS = [("100k", "100k_REPEAT"), ("47k", "47k_REPEAT"), ("22k", "22k_REPEAT"), ("10k", "10k_REPEAT")]
NOMINAL_R = {
    "10k": 10_000.0,
    "22k": 22_000.0,
    "47k": 47_000.0,
    "68k": 68_000.0,
    "100k": 100_000.0,
    "220k": 220_000.0,
    "470k": 470_000.0,
    "1p5M": 1_500_000.0,
}
MEASURED_KEY = {
    "10k": "R10_measured_ohm",
    "22k": "R22_measured_ohm",
    "47k": "R47_measured_ohm",
    "68k": "R68_measured_ohm",
    "100k": "R100_measured_ohm",
    "220k": "R220_measured_ohm",
    "470k": "R470_measured_ohm",
    "1p5M": "R1p5M_measured_ohm",
}


def mad(values: np.ndarray) -> float:
    median = float(np.median(values))
    return float(np.median(np.abs(values - median)))


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def condition_base(condition: str) -> str:
    return condition.replace("_REPEAT", "")


def measured_r(condition: str, metadata: dict) -> tuple[Optional[float], float, str]:
    base = condition_base(condition)
    nominal = NOMINAL_R.get(base)
    if nominal is None:
        return None, math.nan, "OPEN"
    measurements = metadata.get("measurements", {})
    value = measurements.get(MEASURED_KEY[base])
    status = measurements.get(f"{MEASURED_KEY[base]}_status", "UNKNOWN")
    if isinstance(value, (int, float)) and value > 0:
        return nominal, float(value), str(status)
    return nominal, nominal, "NOMINAL_USED"


def measured_value(metadata: dict, key: str, default: float) -> float:
    value = metadata.get("measurements", {}).get(key)
    return float(value) if isinstance(value, (int, float)) and value > 0 else default


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def summarize(dataset_dir: Path) -> tuple[list[dict[str, object]], list[dict[str, object]], dict]:
    metadata = json.loads((dataset_dir / "metadata.json").read_text(encoding="utf-8"))
    rows = load_rows(dataset_dir / "raw_all_conditions.csv")
    by_condition: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_condition.setdefault(row["condition"], []).append(row)

    vdda = measured_value(metadata, "3V3_pre_v", 3.3)
    vref = measured_value(metadata, "VREF_pre_v", 1.03)
    rf = measured_value(metadata, "Rf_measured_ohm", 10_000.0)
    full_scale = 65535.0

    summary: list[dict[str, object]] = []
    control_rows: list[dict[str, object]] = []
    condition_means = {}

    for condition, condition_rows in by_condition.items():
        c0 = np.array([float(row["c0_raw"]) for row in condition_rows], dtype=float)
        mean_raw = float(np.mean(c0))
        std_raw = float(np.std(c0, ddof=1))
        mean_voltage = mean_raw * vdda / full_scale
        std_voltage = std_raw * vdda / full_scale
        delta_v = mean_voltage - vref
        nominal, r_used, r_status = measured_r(condition, metadata)
        inv_r = 0.0 if nominal is None else 1.0 / r_used
        theory_delta = 0.0 if nominal is None else vref * rf / r_used
        residual = delta_v - theory_delta
        rel_error = math.nan if nominal is None or abs(theory_delta) < 1e-12 else 100.0 * residual / theory_delta
        condition_means[condition] = {"c0": mean_raw, **{f"c{c}": float(np.mean([float(row[f'c{c}_raw']) for row in condition_rows])) for c in range(1, 8)}}

        summary.append(
            {
                "condition": condition,
                "sample_count": len(c0),
                "mean_raw": round(mean_raw, 6),
                "std_raw": round(std_raw, 6),
                "median_raw": round(float(np.median(c0)), 6),
                "MAD_raw": round(mad(c0), 6),
                "min_raw": int(np.min(c0)),
                "max_raw": int(np.max(c0)),
                "p2p_raw": int(np.max(c0) - np.min(c0)),
                "mean_voltage": round(mean_voltage, 9),
                "std_voltage": round(std_voltage, 9),
                "delta_v_mean": round(delta_v, 9),
                "delta_v_std": round(std_voltage, 9),
                "nominal_R": "" if nominal is None else round(nominal, 6),
                "measured_R": "" if nominal is None else round(r_used, 6),
                "measured_R_status": r_status,
                "inv_R": "" if nominal is None else f"{inv_r:.12g}",
                "theoretical_delta_v": round(theory_delta, 9),
                "residual_v": round(residual, 9),
                "relative_error_percent": "" if math.isnan(rel_error) else round(rel_error, 6),
            }
        )

        for col in range(1, 8):
            values = np.array([float(row[f"c{col}_raw"]) for row in condition_rows], dtype=float)
            control_rows.append(
                {
                    "condition": condition,
                    "channel": f"COL{col}",
                    "mean_raw": round(float(np.mean(values)), 6),
                    "std_raw": round(float(np.std(values, ddof=1)), 6),
                    "min_raw": int(np.min(values)),
                    "max_raw": int(np.max(values)),
                    "p2p_raw": int(np.max(values) - np.min(values)),
                }
            )

    c0_means = np.array([condition_means[c]["c0"] for c in by_condition], dtype=float)
    for col in range(1, 8):
        values = np.array([condition_means[c][f"c{col}"] for c in by_condition], dtype=float)
        corr = float(np.corrcoef(c0_means, values)[0, 1]) if len(values) > 1 and np.std(values) > 0 else math.nan
        control_rows.append({"condition": "ALL_CONDITIONS", "channel": f"COL{col}", "mean_raw": "", "std_raw": "", "min_raw": "", "max_raw": "", "p2p_raw": "", "corr_with_col0_condition_mean": round(corr, 6) if not math.isnan(corr) else ""})

    return summary, control_rows, metadata


def fit_and_repeatability(summary: list[dict[str, object]], metadata: dict) -> dict:
    by_condition = {str(row["condition"]): row for row in summary}
    fit_rows = [by_condition[name] for name in NON_OPEN_PRIMARY if name in by_condition]
    x = np.array([float(row["inv_R"]) for row in fit_rows], dtype=float)
    y = np.array([float(row["delta_v_mean"]) for row in fit_rows], dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    predicted = slope * x + intercept
    ss_res = float(np.sum((y - predicted) ** 2))
    ss_tot = float(np.sum((y - float(np.mean(y))) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else math.nan
    vref = measured_value(metadata, "VREF_pre_v", 1.03)
    rf_eff = slope / vref if vref else math.nan
    rf_measured = measured_value(metadata, "Rf_measured_ohm", 10_000.0)

    repeatability = {}
    for first, repeat in REPEAT_PAIRS:
        if first not in by_condition or repeat not in by_condition:
            continue
        a = float(by_condition[first]["mean_voltage"])
        b = float(by_condition[repeat]["mean_voltage"])
        sd_a = float(by_condition[first]["std_voltage"])
        sd_b = float(by_condition[repeat]["std_voltage"])
        diff = b - a
        repeatability[first] = {
            "first": first,
            "repeat": repeat,
            "mean_voltage_diff": diff,
            "percent_diff_vs_first": math.nan if abs(a) < 1e-12 else 100.0 * diff / a,
            "std_voltage_diff": sd_b - sd_a,
        }

    return {
        "slope": float(slope),
        "intercept": float(intercept),
        "r_squared": float(r2),
        "rf_eff_ohm": float(rf_eff),
        "rf_measured_ohm": float(rf_measured),
        "rf_eff_error_percent": math.nan if abs(rf_measured) < 1e-12 else 100.0 * (rf_eff - rf_measured) / rf_measured,
        "repeatability": repeatability,
    }


def make_plots(dataset_dir: Path, summary: list[dict[str, object]], fit: dict, metadata: dict) -> None:
    plots = dataset_dir / "plots"
    plots.mkdir(parents=True, exist_ok=True)
    by_condition = {str(row["condition"]): row for row in summary}
    primary = [by_condition[name] for name in NON_OPEN_PRIMARY if name in by_condition]
    vref = measured_value(metadata, "VREF_pre_v", 1.03)
    rf = measured_value(metadata, "Rf_measured_ohm", 10_000.0)

    r = np.array([float(row["measured_R"]) for row in primary])
    inv_r = np.array([float(row["inv_R"]) for row in primary])
    delta = np.array([float(row["delta_v_mean"]) for row in primary])
    theory = vref * rf / r
    fit_y = fit["slope"] * inv_r + fit["intercept"]

    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    ax.scatter(inv_r, delta, label="measured", color="#1976d2")
    ax.plot(inv_r, theory, label="theory", color="#555555", linestyle="--")
    ax.plot(inv_r, fit_y, label="fit", color="#d32f2f")
    ax.set_xlabel("1 / R (1/ohm)")
    ax.set_ylabel("Delta V (V)")
    ax.set_title(f"Delta V vs 1/R, R2={fit['r_squared']:.6f}")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(plots / "01_deltaV_vs_inverseR.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    ax.plot(r, [float(row["mean_voltage"]) for row in primary], marker="o")
    ax.set_xscale("log")
    ax.set_xlabel("Rtest (ohm, log)")
    ax.set_ylabel("Vout (V)")
    ax.set_title("COL0 Vout vs R")
    ax.grid(True, which="both", alpha=0.3)
    fig.tight_layout()
    fig.savefig(plots / "02_vout_vs_R_logx.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    ax.axhline(0, color="#555555", linewidth=1)
    ax.plot(r, delta - theory, marker="o", color="#c2185b")
    ax.set_xscale("log")
    ax.set_xlabel("Rtest (ohm, log)")
    ax.set_ylabel("Residual (V)")
    ax.set_title("Measured Delta V - Theory")
    ax.grid(True, which="both", alpha=0.3)
    fig.tight_layout()
    fig.savefig(plots / "03_residual_vs_R.png", dpi=160)
    plt.close(fig)

    labels, first_values, repeat_values = [], [], []
    for first, repeat in REPEAT_PAIRS:
        if first in by_condition and repeat in by_condition:
            labels.append(first)
            first_values.append(float(by_condition[first]["mean_voltage"]))
            repeat_values.append(float(by_condition[repeat]["mean_voltage"]))
    x_pos = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    ax.bar(x_pos - 0.18, first_values, width=0.36, label="first")
    ax.bar(x_pos + 0.18, repeat_values, width=0.36, label="repeat")
    ax.set_xticks(x_pos, labels)
    ax.set_ylabel("Vout (V)")
    ax.set_title("Repeatability")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(plots / "04_repeatability_10_22_47_100k.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    offset = 0
    for condition in [row["condition"] for row in summary]:
        path = dataset_dir / f"{condition}.csv"
        if not path.exists():
            continue
        rows = load_rows(path)
        y_values = [int(row["c0_raw"]) for row in rows]
        ax.plot(np.arange(len(y_values)) + offset, y_values, linewidth=0.8, label=condition)
        offset += len(y_values)
    ax.set_xlabel("Sample index, concatenated")
    ax.set_ylabel("COL0 raw")
    ax.set_title("COL0 time trace, all conditions")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(plots / "05_col0_time_trace_all_conditions.png", dpi=160)
    plt.close(fig)

    control_summary = load_rows(dataset_dir / "control_channels_summary.csv")
    labels = [f"COL{col}" for col in range(1, 8)]
    stds = []
    for col in labels:
        values = [float(row["std_raw"]) for row in control_summary if row["channel"] == col and row["condition"] != "ALL_CONDITIONS" and row["std_raw"]]
        stds.append(float(np.mean(values)) if values else 0.0)
    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    ax.bar(labels, stds, color="#455a64")
    ax.set_ylabel("Mean std raw")
    ax.set_title("Control channel noise, COL1..COL7")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(plots / "06_control_channels_std.png", dpi=160)
    plt.close(fig)


def classify(summary: list[dict[str, object]], fit: dict, control_rows: list[dict[str, object]]) -> tuple[str, list[str]]:
    reasons = []
    by_condition = {str(row["condition"]): row for row in summary}
    primary = [by_condition[name] for name in NON_OPEN_PRIMARY if name in by_condition]
    # Sequence is high R -> low R. Vout should move away from VREF as R decreases.
    vouts = [float(row["mean_voltage"]) for row in primary]
    if any(vouts[i + 1] <= vouts[i] for i in range(len(vouts) - 1)):
        reasons.append("COL0 mean Vout is not strictly increasing as R decreases from 1.5M to 10k.")
    if "47k" in by_condition and abs(float(by_condition["47k"]["delta_v_mean"])) < 0.02:
        reasons.append("47k dropped near VREF.")
    if "100k" in by_condition and abs(float(by_condition["100k"]["delta_v_mean"])) < 0.02:
        reasons.append("100k dropped near VREF.")
    if not math.isnan(float(fit["r_squared"])) and float(fit["r_squared"]) < 0.995:
        reasons.append(f"R2 < 0.995 ({fit['r_squared']:.6f}).")
    for label, item in fit.get("repeatability", {}).items():
        if abs(float(item["percent_diff_vs_first"])) > 5.0:
            reasons.append(f"{label} repeatability differs by >5%.")
    control_corr = [row for row in control_rows if row.get("condition") == "ALL_CONDITIONS"]
    abnormal = [row for row in control_corr if row.get("corr_with_col0_condition_mean") not in ("", None) and abs(float(row["corr_with_col0_condition_mean"])) > 0.8]
    if abnormal:
        reasons.append("COL1..COL7 have high correlation with COL0 condition means.")
    return ("FAIL" if reasons else "PASS"), reasons


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze ORDER-ARCH-01A direct TIA dataset.")
    parser.add_argument("dataset_dir", type=Path)
    args = parser.parse_args()
    dataset_dir = args.dataset_dir.resolve()

    summary, control_rows, metadata = summarize(dataset_dir)
    write_csv(dataset_dir / "analysis_summary.csv", summary)
    write_csv(dataset_dir / "control_channels_summary.csv", control_rows)
    fit = fit_and_repeatability(summary, metadata)
    status, reasons = classify(summary, fit, control_rows)
    fit["status"] = status
    fit["fail_reasons"] = reasons
    (dataset_dir / "fit_results.json").write_text(json.dumps(fit, indent=2), encoding="utf-8")
    make_plots(dataset_dir, summary, fit, metadata)

    print(f"Dataset: {dataset_dir}")
    print(f"STATUS: {status}")
    print(f"R2: {fit['r_squared']:.6f}")
    print(f"Rf_eff: {fit['rf_eff_ohm']:.3f} ohm")
    if reasons:
        print("Reasons:")
        for reason in reasons:
            print(f"- {reason}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
