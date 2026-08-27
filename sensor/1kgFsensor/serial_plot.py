import argparse
import re
import time
from collections import deque

import matplotlib.animation as animation
import matplotlib.pyplot as plt
import serial


CSV_RE = re.compile(r"^\s*(-?\d+)\s*,\s*(-?\d+)\s*$")
RAW_RE = re.compile(r"\braw=(-?\d+)\b")


def main():
    parser = argparse.ArgumentParser(description="Live plot HX711 serial output.")
    parser.add_argument("--port", default="COM6")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--window", type=int, default=200, help="Number of samples to display.")
    args = parser.parse_args()

    ser = serial.Serial(args.port, args.baud, timeout=0.05)
    time.sleep(2.0)

    xs = deque(maxlen=args.window)
    raw_values = deque(maxlen=args.window)
    delta_values = deque(maxlen=args.window)
    sample_index = 0
    baseline = None
    last_status = ""

    fig, ax = plt.subplots()
    raw_line, = ax.plot([], [], label="raw")
    delta_line, = ax.plot([], [], label="delta")
    ax.set_title(f"Serial HX711 board - {args.port} @ {args.baud}")
    ax.set_xlabel("sample")
    ax.set_ylabel("ADC counts")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left")

    def update(_frame):
        nonlocal sample_index, baseline, last_status

        for _ in range(30):
            raw_line_bytes = ser.readline()
            if not raw_line_bytes:
                break

            text = raw_line_bytes.decode("utf-8", errors="replace").strip()
            csv_match = CSV_RE.match(text)
            raw_match = RAW_RE.search(text)
            if csv_match:
                raw, delta = map(int, csv_match.groups())
                if baseline is None:
                    baseline = raw - delta
                xs.append(sample_index)
                raw_values.append(raw)
                delta_values.append(delta)
                sample_index += 1
            elif raw_match:
                raw = int(raw_match.group(1))
                if baseline is None:
                    baseline = raw
                delta = raw - baseline
                xs.append(sample_index)
                raw_values.append(raw)
                delta_values.append(delta)
                sample_index += 1
            elif text and text != last_status:
                print(text)
                last_status = text

        if not xs:
            return raw_line, tared_line

        raw_line.set_data(xs, raw_values)
        delta_line.set_data(xs, delta_values)
        ax.set_xlim(xs[0], xs[-1] if xs[-1] > xs[0] else xs[0] + 1)

        all_values = list(raw_values) + list(delta_values)
        ymin = min(all_values)
        ymax = max(all_values)
        pad = max(100, int((ymax - ymin) * 0.1))
        ax.set_ylim(ymin - pad, ymax + pad)

        return raw_line, delta_line

    try:
        animation.FuncAnimation(fig, update, interval=100, blit=False, cache_frame_data=False)
        plt.show()
    finally:
        ser.close()


if __name__ == "__main__":
    main()
