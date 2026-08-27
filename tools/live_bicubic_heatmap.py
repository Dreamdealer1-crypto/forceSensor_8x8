#!/usr/bin/env python3
"""Run the low-latency 8x8 to 32x32 Bicubic live heatmap."""

from live_interp_core import run


if __name__ == "__main__":
    raise SystemExit(run("bicubic"))

