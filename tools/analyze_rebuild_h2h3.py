#!/usr/bin/env python3
"""Analyze ORDER-REBUILD-H2/H3 captures.

H2 analysis is implemented now. H3 analysis will be enabled after the fixture
and capture sequence are ready.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def analyze_h2(dataset_dir: Path, min_mv: float, max_mv: float) -> dict[str, object]:
    rows = load_rows(dataset_dir / "h2_row_scan.csv")
    if not rows:
        raise RuntimeError("h2_row_scan.csv is empty")

    values = np.array([[float(row[f"c{col}_mv"]) for col in range(8)] for row in rows], dtype=float)
    row_ids = np.array([int(row["row"]) for row in rows], dtype=int)
    frames = sorted({int(row["frame"]) for row in rows})

    anomalies = []
    point_rows: list[dict[str, object]] = []
    for row_index, row in enumerate(rows):
        for col in range(8):
            value = float(row[f"c{col}_mv"])
            status = "PASS" if min_mv <= value <= max_mv else "FAIL"
            if status == "FAIL":
                anomalies.append({"frame": int(row["frame"]), "row": int(row["row"]), "col": col, "mv": value})
            point_rows.append(
                {
                    "frame": int(row["frame"]),
                    "row": int(row["row"]),
                    "col": col,
                    "mv": f"{value:.3f}",
                    "status": status,
                }
            )

    row_summary = []
    for row in range(8):
        row_values = values[row_ids == row]
        if row_values.size == 0:
            row_summary.append({"row": row, "samples": 0, "status": "MISSING"})
            anomalies.append({"row": row, "issue": "missing row"})
            continue
        row_summary.append(
            {
                "row": row,
                "samples": int(row_values.shape[0]),
                "min_mv": f"{float(np.min(row_values)):.3f}",
                "max_mv": f"{float(np.max(row_values)):.3f}",
                "mean_mv": f"{float(np.mean(row_values)):.3f}",
                "std_mv": f"{float(np.std(row_values, ddof=1)) if row_values.size > 1 else 0.0:.3f}",
                "status": "PASS" if np.all((row_values >= min_mv) & (row_values <= max_mv)) else "FAIL",
            }
        )

    repeat_max_abs_diff = None
    if len(frames) >= 2:
        frame0 = {int(row["row"]): row for row in rows if int(row["frame"]) == frames[0]}
        frame1 = {int(row["row"]): row for row in rows if int(row["frame"]) == frames[1]}
        diffs = []
        for row in range(8):
            if row not in frame0 or row not in frame1:
                continue
            for col in range(8):
                diffs.append(abs(float(frame1[row][f"c{col}_mv"]) - float(frame0[row][f"c{col}_mv"])))
        if diffs:
            repeat_max_abs_diff = float(max(diffs))

    status = "PASS" if not anomalies and len({int(row["row"]) for row in rows}) == 8 and len(rows) >= 16 else "FAIL"
    summary = {
        "order": "ORDER-REBUILD-H2H3",
        "phase": "H2",
        "status": status,
        "frames": frames,
        "row_records": len(rows),
        "point_count": len(point_rows),
        "pass_window_mv": [min_mv, max_mv],
        "min_mv": float(np.min(values)),
        "max_mv": float(np.max(values)),
        "mean_mv": float(np.mean(values)),
        "repeat_max_abs_diff_mv": repeat_max_abs_diff,
        "anomaly_count": len(anomalies),
        "anomalies": anomalies[:100],
    }

    write_csv(dataset_dir / "h2_point_summary.csv", point_rows)
    write_csv(dataset_dir / "h2_row_summary.csv", row_summary)
    (dataset_dir / "analysis_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    make_h2_figures(dataset_dir, rows, values, min_mv, max_mv, summary)
    return summary


def summarize_matrix(rows: list[dict[str, str]]) -> tuple[np.ndarray, np.ndarray]:
    matrix = np.zeros((8, 8), dtype=float)
    std = np.zeros((8, 8), dtype=float)
    for row_id in range(8):
        row_records = [row for row in rows if int(row["row"]) == row_id]
        if not row_records:
            matrix[row_id, :] = np.nan
            std[row_id, :] = np.nan
            continue
        values = np.array([[float(row[f"c{col}_mv"]) for col in range(8)] for row in row_records], dtype=float)
        matrix[row_id, :] = np.mean(values, axis=0)
        std[row_id, :] = np.std(values, axis=0, ddof=1) if len(row_records) > 1 else 0.0
    return matrix, std


def analyze_h3(dataset_dir: Path) -> dict[str, object]:
    results: dict[str, object] = {
        "order": "ORDER-REBUILD-H2H3",
        "phase": "H3",
        "subarray": {"rows": [2, 3], "cols": [4, 5]},
        "experiments": {},
    }
    exp_files = {
        "A": dataset_dir / "h3_exp_a.csv",
        "B": dataset_dir / "h3_exp_b.csv",
        "C": dataset_dir / "h3_exp_c.csv",
    }
    matrices: dict[str, np.ndarray] = {}
    for exp, path in exp_files.items():
        if not path.exists():
            continue
        rows = load_rows(path)
        matrix, std = summarize_matrix(rows)
        matrices[exp] = matrix
        vref = float(np.nanmedian(np.concatenate([matrix[:2, :].ravel(), matrix[4:, :].ravel()])))
        exp_result: dict[str, object] = {
            "file": str(path),
            "frames": len(rows) // 8,
            "vref_estimate_mv": vref,
            "row2_c4_mv": float(matrix[2, 4]),
            "row2_c5_mv": float(matrix[2, 5]),
            "row3_c4_mv": float(matrix[3, 4]),
            "row3_c5_mv": float(matrix[3, 5]),
            "std_row2_c4_mv": float(std[2, 4]),
            "std_row2_c5_mv": float(std[2, 5]),
            "std_row3_c4_mv": float(std[3, 4]),
            "std_row3_c5_mv": float(std[3, 5]),
        }
        if exp == "A":
            target = abs(float(matrix[2, 4]) - vref)
            ghost_candidates = [
                abs(float(matrix[2, 5]) - vref),
                abs(float(matrix[3, 4]) - vref),
                abs(float(matrix[3, 5]) - vref),
            ]
            max_non_target = float(np.nanmax(np.abs(matrix - vref)))
            max_non_target = max(ghost_candidates)
            exp_result["target_delta_mv"] = target
            exp_result["max_local_ghost_delta_mv"] = max_non_target
            exp_result["kghost_local_percent"] = 100.0 * max_non_target / target if target > 1e-9 else None
            exp_result["status"] = "PASS" if target > 50.0 and max_non_target < max(10.0, target * 0.05) else "CHECK"
        results["experiments"][exp] = exp_result

    status = "WAITING_MORE_DATA"
    if "A" in results["experiments"] and len(results["experiments"]) == 1:
        status = str(results["experiments"]["A"].get("status", "CHECK"))
    elif {"A", "B", "C"}.issubset(results["experiments"].keys()):
        status = "READY_FOR_FULL_H3_REVIEW"
    results["status"] = status
    (dataset_dir / "analysis_summary_h3.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    make_h3_figures(dataset_dir, matrices, results)
    return results


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
            "ps.fonttype": 42,
        }
    )


def make_h2_figures(
    dataset_dir: Path,
    rows: list[dict[str, str]],
    values: np.ndarray,
    min_mv: float,
    max_mv: float,
    summary: dict[str, object],
) -> None:
    set_plot_style()
    figure_dir = dataset_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    row_ids = np.array([int(row["row"]) for row in rows], dtype=int)
    frames = sorted({int(row["frame"]) for row in rows})

    mean_matrix = np.zeros((8, 8), dtype=float)
    std_matrix = np.zeros((8, 8), dtype=float)
    for row in range(8):
        row_values = values[row_ids == row]
        mean_matrix[row, :] = np.mean(row_values, axis=0)
        std_matrix[row, :] = np.std(row_values, axis=0, ddof=1) if row_values.shape[0] > 1 else 0.0

    fig, ax = plt.subplots(figsize=(4.2, 3.2), constrained_layout=True)
    image = ax.imshow(mean_matrix, cmap="viridis", vmin=min_mv, vmax=max_mv, aspect="equal")
    ax.set_xlabel("Column")
    ax.set_ylabel("Selected row")
    ax.set_title("H2 row-scan baseline map")
    ax.set_xticks(range(8))
    ax.set_yticks(range(8))
    for row in range(8):
        for col in range(8):
            ax.text(col, row, f"{mean_matrix[row, col]:.1f}", ha="center", va="center", color="white", fontsize=5.5)
    colorbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    colorbar.set_label("Output voltage (mV)")
    ax.text(-0.16, 1.04, "a", transform=ax.transAxes, fontweight="bold", fontsize=11)
    fig.savefig(figure_dir / "h2_row_scan_heatmap.svg", format="svg")
    fig.savefig(figure_dir / "h2_row_scan_heatmap.png", dpi=300)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(4.6, 2.8), constrained_layout=True)
    x = np.arange(8)
    palette = ["#24568f", "#d28b26", "#4f8f3a", "#9b3d3d", "#6b5ca5", "#3c8d8f", "#777777", "#b35b8c"]
    for col in range(8):
        ax.plot(x, mean_matrix[:, col], marker="o", markersize=3.2, linewidth=1.0, color=palette[col], label=f"c{col}")
    ax.axhspan(min_mv, max_mv, color="#dfe8d5", alpha=0.5, linewidth=0)
    ax.set_xlabel("Selected row")
    ax.set_ylabel("Output voltage (mV)")
    ax.set_title("H2 per-column response during row switching")
    ax.set_xticks(range(8))
    ax.grid(True, color="#d9d9d9", linewidth=0.5)
    ax.legend(ncol=4, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.20))
    ax.text(-0.12, 1.05, "b", transform=ax.transAxes, fontweight="bold", fontsize=11)
    fig.savefig(figure_dir / "h2_column_traces.svg", format="svg")
    fig.savefig(figure_dir / "h2_column_traces.png", dpi=300)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.9), constrained_layout=True)
    axes[0].bar(range(8), np.max(mean_matrix, axis=1) - np.min(mean_matrix, axis=1), color="#24568f", width=0.65)
    axes[0].set_xlabel("Selected row")
    axes[0].set_ylabel("Within-row span (mV)")
    axes[0].set_title("Row uniformity")
    axes[0].set_xticks(range(8))
    axes[0].grid(True, axis="y", color="#d9d9d9", linewidth=0.5)
    axes[0].text(-0.16, 1.05, "c", transform=axes[0].transAxes, fontweight="bold", fontsize=11)

    axes[1].bar(range(8), np.mean(std_matrix, axis=0), color="#d28b26", width=0.65)
    axes[1].set_xlabel("Column")
    axes[1].set_ylabel("Frame-to-frame SD (mV)")
    axes[1].set_title("Two-frame repeatability")
    axes[1].set_xticks(range(8))
    axes[1].grid(True, axis="y", color="#d9d9d9", linewidth=0.5)
    axes[1].text(-0.16, 1.05, "d", transform=axes[1].transAxes, fontweight="bold", fontsize=11)
    fig.savefig(figure_dir / "h2_uniformity_repeatability.svg", format="svg")
    fig.savefig(figure_dir / "h2_uniformity_repeatability.png", dpi=300)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.2, 4.05), constrained_layout=True)
    ax.axis("off")
    status = str(summary["status"])
    lines = [
        "ORDER-REBUILD-H2 row-scan verification",
        f"Status: {status}",
        f"64-point range: {summary['min_mv']:.3f} to {summary['max_mv']:.3f} mV",
        f"Records: {summary['row_records']} rows / {summary['point_count']} points",
        f"Repeat max abs diff: {summary['repeat_max_abs_diff_mv']:.3f} mV",
        f"Anomalies: {summary['anomaly_count']}",
    ]
    ax.text(0.04, 0.86, lines[0], fontsize=17, fontweight="bold", transform=ax.transAxes)
    ax.text(0.04, 0.70, "\n".join(lines[1:]), fontsize=11, linespacing=1.7, transform=ax.transAxes)
    inset = ax.inset_axes([0.58, 0.18, 0.36, 0.62])
    image = inset.imshow(mean_matrix, cmap="viridis", vmin=min_mv, vmax=max_mv, aspect="equal")
    inset.set_xticks(range(8))
    inset.set_yticks(range(8))
    inset.set_xlabel("COL")
    inset.set_ylabel("ROW")
    fig.colorbar(image, ax=inset, fraction=0.046, pad=0.04).set_label("mV")
    fig.savefig(figure_dir / "h2_ppt_summary_16x9.svg", format="svg")
    fig.savefig(figure_dir / "h2_ppt_summary_16x9.png", dpi=300)
    plt.close(fig)

    readme = (
        "# ORDER-REBUILD-H2 figures\n\n"
        "- `h2_ppt_summary_16x9.svg`: PPT summary slide figure.\n"
        "- `h2_row_scan_heatmap.svg`: 8x8 row/column baseline heatmap.\n"
        "- `h2_column_traces.svg`: per-column voltages during ROW0-ROW7 switching.\n"
        "- `h2_uniformity_repeatability.svg`: row uniformity and two-frame repeatability.\n"
    )
    (figure_dir / "README.md").write_text(readme, encoding="utf-8")


def make_h3_figures(dataset_dir: Path, matrices: dict[str, np.ndarray], results: dict[str, object]) -> None:
    if not matrices:
        return
    set_plot_style()
    figure_dir = dataset_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    for exp, matrix in matrices.items():
        vref = float(results["experiments"][exp]["vref_estimate_mv"])
        vmax = max(float(np.nanmax(matrix)), vref + 250.0)
        fig, ax = plt.subplots(figsize=(4.2, 3.2), constrained_layout=True)
        image = ax.imshow(matrix, cmap="viridis", vmin=vref - 10.0, vmax=vmax, aspect="equal")
        ax.set_xlabel("Column")
        ax.set_ylabel("Selected row")
        ax.set_title(f"H3 experiment {exp}: ROW2/3 x COL4/5")
        ax.set_xticks(range(8))
        ax.set_yticks(range(8))
        for row in range(8):
            for col in range(8):
                color = "white" if matrix[row, col] > (vref + 60.0) else "#111111"
                ax.text(col, row, f"{matrix[row, col]:.0f}", ha="center", va="center", color=color, fontsize=5.5)
        ax.add_patch(plt.Rectangle((3.5, 1.5), 2, 2, fill=False, edgecolor="#d62728", linewidth=1.3))
        colorbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
        colorbar.set_label("Output voltage (mV)")
        ax.text(-0.16, 1.04, exp.lower(), transform=ax.transAxes, fontweight="bold", fontsize=11)
        fig.savefig(figure_dir / f"h3_heatmap_exp_{exp.lower()}.svg", format="svg")
        fig.savefig(figure_dir / f"h3_heatmap_exp_{exp.lower()}.png", dpi=300)
        plt.close(fig)

    labels = []
    values = []
    colors = []
    for exp in ["A", "B", "C"]:
        if exp not in results["experiments"]:
            continue
        exp_result = results["experiments"][exp]
        vref = float(exp_result["vref_estimate_mv"])
        for key, label, color in [
            ("row2_c4_mv", "R2-c4", "#24568f"),
            ("row2_c5_mv", "R2-c5", "#d28b26"),
            ("row3_c4_mv", "R3-c4", "#4f8f3a"),
            ("row3_c5_mv", "R3-c5", "#9b3d3d"),
        ]:
            labels.append(f"{exp}\n{label}")
            values.append(float(exp_result[key]) - vref)
            colors.append(color)
    if labels:
        fig, ax = plt.subplots(figsize=(max(4.6, len(labels) * 0.45), 2.9), constrained_layout=True)
        ax.bar(range(len(labels)), values, color=colors, width=0.72)
        ax.axhline(0, color="#333333", linewidth=0.8)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels)
        ax.set_ylabel("Delta from VREF (mV)")
        ax.set_title("H3 target and local ghost response")
        ax.grid(True, axis="y", color="#d9d9d9", linewidth=0.5)
        fig.savefig(figure_dir / "h3_local_response_bar.svg", format="svg")
        fig.savefig(figure_dir / "h3_local_response_bar.png", dpi=300)
        plt.close(fig)

    readme = (
        "# ORDER-REBUILD-H3 figures\n\n"
        "- `h3_heatmap_exp_a.svg`: experiment A 8x8 voltage heatmap.\n"
        "- `h3_heatmap_exp_b.svg`: experiment B heatmap, generated when data exists.\n"
        "- `h3_heatmap_exp_c.svg`: experiment C heatmap, generated when data exists.\n"
        "- `h3_local_response_bar.svg`: ROW2/3-COL4/5 local target/ghost comparison.\n"
    )
    (figure_dir / "README_H3.md").write_text(readme, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_dir", type=Path)
    parser.add_argument("--phase", choices=["h2", "h3"], default="h2")
    parser.add_argument("--min-mv", type=float, default=1020.0)
    parser.add_argument("--max-mv", type=float, default=1060.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.phase == "h3":
        summary = analyze_h3(args.dataset_dir.resolve())
        print("ORDER-REBUILD-H3 RESULT")
        print(f"STATUS: {summary['status']}")
        for exp, exp_result in summary["experiments"].items():
            print(f"Experiment {exp}: frames={exp_result['frames']}")
            print(
                "  ROW2-c4={:.3f}mV, ROW2-c5={:.3f}mV, ROW3-c4={:.3f}mV, ROW3-c5={:.3f}mV".format(
                    exp_result["row2_c4_mv"],
                    exp_result["row2_c5_mv"],
                    exp_result["row3_c4_mv"],
                    exp_result["row3_c5_mv"],
                )
            )
            if "kghost_local_percent" in exp_result:
                print(f"  Kghost_local={exp_result['kghost_local_percent']:.3f}%")
        return 0
    summary = analyze_h2(args.dataset_dir.resolve(), args.min_mv, args.max_mv)
    print("ORDER-REBUILD-H2 RESULT")
    print(f"STATUS: {summary['status']}")
    print(f"64-point range: min={summary['min_mv']:.3f}mV, max={summary['max_mv']:.3f}mV")
    print(f"Row records: {summary['row_records']}, points: {summary['point_count']}")
    print(f"Repeat max abs diff: {summary['repeat_max_abs_diff_mv']}")
    print(f"Anomalies: {summary['anomaly_count']}")
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
