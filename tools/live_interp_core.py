#!/usr/bin/env python3
"""Shared low-latency live interpolation display for the 8x8 sensor matrix."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from scipy.ndimage import zoom

from live_rebuild_h4_unlimited import (
    apply_display_map,
    collect_baseline,
    load_baseline,
    parse_serial_frame,
    raw_to_display_rc,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "data/rebuild_h4/20260818_real_sensor_run01/baseline_stats.json"


@dataclass
class InterpolationResult:
    mean: np.ndarray
    std: np.ndarray | None = None


class FixedGridGPR:
    """Fast GP prediction with a fixed kernel and precomputed grid weights.

    The 8x8 sample coordinates never change, so the expensive 64x64 solve is
    precomputed once. Each live frame then needs only matrix multiplication.
    """

    def __init__(self, scale: int, length_scale: float, noise_ratio: float, signal_std_mv: float):
        rows = cols = 8
        sample_y, sample_x = np.meshgrid(np.arange(rows), np.arange(cols), indexing="ij")
        train = np.column_stack((sample_y.ravel(), sample_x.ravel())).astype(float)
        fine_y = np.linspace(0.0, rows - 1, rows * scale)
        fine_x = np.linspace(0.0, cols - 1, cols * scale)
        pred_y, pred_x = np.meshgrid(fine_y, fine_x, indexing="ij")
        pred = np.column_stack((pred_y.ravel(), pred_x.ravel()))

        def rbf(a: np.ndarray, b: np.ndarray) -> np.ndarray:
            squared = np.sum((a[:, None, :] - b[None, :, :]) ** 2, axis=2)
            return np.exp(-0.5 * squared / (length_scale**2))

        k_train = rbf(train, train)
        k_train.flat[:: k_train.shape[0] + 1] += noise_ratio
        k_pred = rbf(pred, train)
        self.weights = np.linalg.solve(k_train, k_pred.T).T
        variance = np.maximum(0.0, 1.0 - np.sum(self.weights * k_pred, axis=1))
        self.std = np.sqrt(variance).reshape(rows * scale, cols * scale) * signal_std_mv
        self.shape = (rows * scale, cols * scale)

    def predict(self, matrix: np.ndarray) -> InterpolationResult:
        mean = (self.weights @ matrix.ravel()).reshape(self.shape)
        return InterpolationResult(np.clip(mean, 0.0, None), self.std)


def bicubic_interpolator(scale: int) -> Callable[[np.ndarray], InterpolationResult]:
    def interpolate(matrix: np.ndarray) -> InterpolationResult:
        return InterpolationResult(np.clip(zoom(matrix, scale, order=3), 0.0, None))

    return interpolate


def newest_complete_frame(serial_port, vdda_v: float):
    """Read one complete frame, then discard complete frames already queued."""
    newest = parse_serial_frame(serial_port, vdda_v)
    skipped = 0
    while newest is not None and serial_port.in_waiting > 700:
        candidate = parse_serial_frame(serial_port, vdda_v)
        if candidate is None:
            break
        newest = candidate
        skipped += 1
    return newest, skipped


def build_parser(method: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"Low-latency {method} live heatmap for the 8x8 fabric pressure matrix."
    )
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--vdda", type=float, default=3.29)
    parser.add_argument("--scale", type=int, default=4, help="8x8 upsampling factor; default gives 32x32")
    parser.add_argument("--baseline-json", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--baseline-frames", type=int, default=120)
    parser.add_argument("--row-origin", choices=["top", "bottom"], default="top")
    parser.add_argument("--col-origin", choices=["left", "right"], default="right")
    parser.add_argument("--transpose", action="store_true")
    parser.add_argument("--vmin", type=float, default=0.0)
    parser.add_argument("--vmax", type=float, default=1000.0)
    parser.add_argument("--refresh-hz", type=float, default=20.0, help="maximum plot refresh rate")
    parser.add_argument("--peak-threshold", type=float, default=50.0)
    parser.add_argument("--no-cell-grid", action="store_true", help="hide original 8x8 sampling grid")
    if method == "gpr":
        parser.add_argument("--length-scale", type=float, default=1.5, help="RBF length scale in sensor pitches")
        parser.add_argument("--noise-ratio", type=float, default=0.01, help="GP diagonal noise/signal ratio")
        parser.add_argument("--signal-std", type=float, default=1000.0, help="uncertainty scale in mV")
        parser.add_argument("--show-uncertainty", action="store_true")
    return parser


def run(method: str) -> int:
    args = build_parser(method).parse_args()
    if args.scale < 1:
        raise SystemExit("--scale must be >= 1")
    if args.refresh_hz <= 0:
        raise SystemExit("--refresh-hz must be > 0")

    import matplotlib.pyplot as plt
    import serial

    if method == "bicubic":
        interpolate = bicubic_interpolator(args.scale)
        method_label = "Bicubic"
    else:
        gpr = FixedGridGPR(args.scale, args.length_scale, args.noise_ratio, args.signal_std)
        interpolate = gpr.predict
        method_label = f"GPR (RBF l={args.length_scale:g})"

    baseline_path = args.baseline_json.resolve() if args.baseline_json else None
    print(f"ARCH 1.1 live {method_label} heatmap")
    print(f"Port: {args.port} @ {args.baud}; output: {8 * args.scale}x{8 * args.scale}")
    print(
        f"Physical map: ROW0={args.row_origin}, COL0={args.col_origin}, "
        f"transpose={args.transpose}"
    )
    print("Close the window or press Ctrl+C to stop.")

    with serial.Serial(args.port, args.baud, timeout=0.08) as serial_port:
        serial_port.reset_input_buffer()
        if baseline_path and baseline_path.exists():
            baseline_mean, _ = load_baseline(baseline_path)
            print(f"Loaded baseline: {baseline_path}")
        else:
            if baseline_path:
                print(f"Baseline not found: {baseline_path}; collecting a temporary baseline.")
            baseline_mean, _ = collect_baseline(serial_port, args.baseline_frames, args.vdda)

        show_uncertainty = bool(method == "gpr" and args.show_uncertainty)
        if show_uncertainty:
            fig, (ax, uncertainty_ax) = plt.subplots(1, 2, figsize=(10.2, 4.8), constrained_layout=True)
        else:
            fig, ax = plt.subplots(figsize=(6.2, 5.2), constrained_layout=True)
            uncertainty_ax = None

        empty = np.zeros((8 * args.scale, 8 * args.scale))
        image = ax.imshow(
            empty,
            cmap="viridis",
            vmin=args.vmin,
            vmax=args.vmax,
            interpolation="nearest",
            extent=(-0.5, 7.5, 7.5, -0.5),
            aspect="equal",
        )
        fig.colorbar(image, ax=ax, label="Delta voltage (mV)")
        ax.set_xlabel("Physical X index")
        ax.set_ylabel("Physical Y index")
        ax.set_xticks(range(8))
        ax.set_yticks(range(8))
        title = ax.set_title(f"Live {method_label}: waiting for data")
        if not args.no_cell_grid:
            ax.set_xticks(np.arange(-0.5, 8.0, 1.0), minor=True)
            ax.set_yticks(np.arange(-0.5, 8.0, 1.0), minor=True)
            ax.grid(which="minor", color="white", linewidth=0.45, alpha=0.35)
            ax.tick_params(which="minor", bottom=False, left=False)

        uncertainty_image = None
        if uncertainty_ax is not None:
            first = interpolate(np.zeros((8, 8)))
            uncertainty_image = uncertainty_ax.imshow(
                first.std,
                cmap="magma",
                vmin=0.0,
                interpolation="nearest",
                extent=(-0.5, 7.5, 7.5, -0.5),
                aspect="equal",
            )
            fig.colorbar(uncertainty_image, ax=uncertainty_ax, label="Estimated std (mV)")
            uncertainty_ax.set_title("GPR interpolation uncertainty")
            uncertainty_ax.set_xlabel("Physical X index")
            uncertainty_ax.set_ylabel("Physical Y index")
            uncertainty_ax.set_xticks(range(8))
            uncertainty_ax.set_yticks(range(8))

        plt.show(block=False)
        started = time.monotonic()
        last_draw = 0.0
        received = 0
        displayed = 0
        skipped_total = 0
        last_seq = None
        seq_gaps = 0
        min_draw_period = 1.0 / args.refresh_hz

        try:
            while plt.fignum_exists(fig.number):
                frame, skipped = newest_complete_frame(serial_port, args.vdda)
                if frame is None:
                    plt.pause(0.001)
                    continue
                received += skipped + 1
                skipped_total += skipped
                if last_seq is not None and frame.seq > last_seq + 1:
                    seq_gaps += frame.seq - last_seq - 1
                last_seq = frame.seq

                now = time.monotonic()
                if now - last_draw < min_draw_period:
                    continue

                delta_raw = np.clip(frame.matrix_raw - baseline_mean, 0.0, None)
                raw_peak = tuple(int(v) for v in np.unravel_index(np.argmax(delta_raw), delta_raw.shape))
                display_y, display_x = raw_to_display_rc(
                    raw_peak[0], raw_peak[1], args.row_origin, args.col_origin, args.transpose
                )
                display_delta = apply_display_map(
                    delta_raw, args.row_origin, args.col_origin, args.transpose
                )
                result = interpolate(display_delta)
                image.set_data(result.mean)
                peak_delta = float(delta_raw[raw_peak])
                state = "ACTIVE" if peak_delta >= args.peak_threshold else "idle"
                displayed += 1
                elapsed = max(now - started, 1e-6)
                title.set_text(
                    f"Live {method_label} | {state} | peak X{display_x} Y{display_y}: {peak_delta:.0f} mV\n"
                    f"capture {received / elapsed:.1f} fps | display {displayed / elapsed:.1f} fps | "
                    f"dropped backlog {skipped_total} | seq gaps {seq_gaps}"
                )
                if uncertainty_image is not None and result.std is not None:
                    uncertainty_image.set_data(result.std)
                fig.canvas.draw_idle()
                fig.canvas.flush_events()
                plt.pause(0.001)
                last_draw = now
        except KeyboardInterrupt:
            pass

    print(
        json.dumps(
            {
                "method": method,
                "received_frames": received,
                "displayed_frames": displayed,
                "dropped_backlog_frames": skipped_total,
                "sequence_gaps": seq_gaps,
            },
            ensure_ascii=False,
        )
    )
    return 0

