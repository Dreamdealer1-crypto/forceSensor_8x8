#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OPEN - RESIST - OPEN 直接 TIA 传递函数验证脚本（目标：U2A / 软件 COL2 = c2 / r2）

从零编写，未复用既有 capture 脚本。

目的
----
对单个待测电阻 Rtest 执行三段闭环：
  1) OPEN_PRE   —— 空载（Rtest 未接）采 N 帧，得到 TIA 虚参考基线 VREF
  2) RESIST     —— 插入 Rtest 采 N 帧，验证 Vout = VREF * (1 + Rf/Rtest)
  3) OPEN_POST  —— 拔除 Rtest 采 N 帧，验证能回到基线（排除接触/夹具漂移）

冻结硬件（不得改动）
------------------
  U2 Pin2（反相输入） <- Rtest -> GND
  U2 Pin1（输出）     -> PF6 -> ADC3_INP8 -> 软件 COL2（c2 / r2，索引 2）
  U2 Pin3 = VREF；U2 Pin1<->Pin2 = Rf = 10k || Cf = 100p
  传感器 COL2 必须从 U2 Pin2 断开
  4051 关闭（ROW_EN/PG5 = HIGH，无行扫描）

串口格式（自动识别）
------------------
  ADC03A,<seq>,<tick_us>,r0..r7,<8审计字段>,<par>,<m0ar>   （当前固件，ADC-03A DMA）
  A01A,<session>,<seq>,<tick_us>,c0..c7                   （ARCH-01A 直连模式）

用法示例
--------
  python tools/capture_open_resist_open.py --port COM7 --rtest 100000
"""

import argparse
import csv
import json
import os
import statistics
import sys
import time

try:
    import serial
except ImportError:
    print("缺少 pyserial，请先安装：pip install pyserial")
    sys.exit(2)

VDD = 3.29          # VDDA（main.h ADC03A_VDDA_UV = 3290000 uV）
ADC_FULL = 65535.0  # 16-bit
CHANNEL_INDEX = 2   # COL2 = PF6 = ADC3_INP8（r2 / c2）


def parse_frame(line):
    """返回 8 通道 raw 元组；非数据帧返回 None。"""
    line = line.strip()
    if not line:
        return None
    if line.startswith(("BOOT", "CFG", "ADC03A_REG", "ADC03A_MEM",
                        "ADC03A_DECODE", "ERROR", "#")):
        return None
    parts = line.split(",")
    tag = parts[0]
    if tag == "ADC03A" and len(parts) >= 11:
        try:
            return tuple(int(x) for x in parts[3:11])
        except ValueError:
            return None
    if tag == "A01A" and len(parts) >= 12:
        try:
            return tuple(int(x) for x in parts[4:12])
        except ValueError:
            return None
    return None


def capture(ser, n, timeout_s):
    """采集 n 帧，返回 8 通道 raw 的列表（每帧一个 8 元组）。"""
    frames = []
    deadline = time.time() + timeout_s
    while len(frames) < n and time.time() < deadline:
        raw_line = ser.readline()
        try:
            line = raw_line.decode("ascii", errors="ignore")
        except Exception:
            continue
        frame = parse_frame(line)
        if frame is not None:
            frames.append(frame)
    return frames


def raw_stats(values):
    if not values:
        return None
    mean = statistics.mean(values)
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    return {"n": len(values), "mean": mean, "std": std,
            "min": min(values), "max": max(values)}


def to_v(raw, vdd=VDD):
    return raw * vdd / ADC_FULL


def main():
    ap = argparse.ArgumentParser(description="OPEN-RESIST-OPEN 直接TIA传递函数验证")
    ap.add_argument("--port", default="COM7", help="串口号（默认 COM7）")
    ap.add_argument("--baud", type=int, default=115200, help="波特率（默认 115200）")
    ap.add_argument("--channel", type=int, default=CHANNEL_INDEX,
                    help="目标通道索引（默认 2 = COL2/PF6/U2A）")
    ap.add_argument("--rtest", type=float, required=True,
                    help="待测电阻 Rtest（欧姆），例如 100000")
    ap.add_argument("--rf", type=float, default=10170.0,
                    help="反馈电阻 Rf（欧姆，默认 10170 = 实测 10.17k）")
    ap.add_argument("--samples", type=int, default=200,
                    help="每段采集帧数（默认 200 ≈ 2 秒 @10ms 周期）")
    ap.add_argument("--timeout", type=float, default=30.0,
                    help="每段采集超时（秒，默认 30）")
    ap.add_argument("--vdd", type=float, default=VDD, help="VDDA 伏特（默认 3.29）")
    ap.add_argument("--out", default=None,
                    help="输出目录（默认 data/open_resist_open/<时间戳>/）")
    args = ap.parse_args()

    if args.rtest <= 0:
        ap.error("--rtest 必须为正数（欧姆）")

    out_dir = args.out
    if out_dir is None:
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_dir = os.path.join("data", "open_resist_open", ts)
    os.makedirs(out_dir, exist_ok=True)

    ser = serial.Serial(args.port, args.baud, timeout=1.0)
    time.sleep(1.0)
    ser.reset_input_buffer()

    phases = [
        ("OPEN_PRE", "确保空载（Rtest 未接、传感器 COL2 已从 U2 Pin2 断开），回车开始采集..."),
        ("RESIST", "插入 Rtest = %.0f 欧姆 到 U2 Pin2 <-> GND，回车开始采集..." % args.rtest),
        ("OPEN_POST", "拔除 Rtest（恢复空载），回车开始采集..."),
    ]
    results = {}

    for name, prompt in phases:
        input(">> " + prompt)
        frames = capture(ser, args.samples, args.timeout)
        if len(frames) < max(1, args.samples // 2):
            print("[警告] 该段只采到 %d 帧（目标 %d），检查串口/接线"
                  % (len(frames), args.samples))

        target_vals = [f[args.channel] for f in frames]
        target = raw_stats(target_vals)
        results[name] = {"target": target,
                         "channels": [raw_stats([f[c] for f in frames])
                                      for c in range(8)]}

        csv_path = os.path.join(out_dir, name + ".csv")
        with open(csv_path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["frame"] + ["c%d" % c for c in range(8)])
            for i, f in enumerate(frames):
                w.writerow([i] + list(f))

        if target:
            print("  %-9s n=%d  raw mean=%.1f  std=%.1f  ->  %.4f V"
                  % (name, target["n"], target["mean"], target["std"],
                     to_v(target["mean"], args.vdd)))
            others = ", ".join(
                "c%d=%.1f" % (c, ch["mean"]) for c, ch in
                enumerate(results[name]["channels"]) if ch and c != args.channel)
            print("          对照通道 raw: " + others)
        else:
            print("  %-9s 未采到任何有效帧！" % name)

    pre = results["OPEN_PRE"]["target"]
    res = results["RESIST"]["target"]
    post = results["OPEN_POST"]["target"]

    verdict = "FAIL"
    if pre and res and post:
        vref = to_v(pre["mean"], args.vdd)
        exp_vout = vref * (1.0 + args.rf / args.rtest)
        exp_dv = vref * args.rf / args.rtest
        got_vout = to_v(res["mean"], args.vdd)
        got_dv = got_vout - vref

        dv_ratio = (got_dv / exp_dv) if exp_dv > 0 else float("inf")
        lift_ok = (0.85 <= dv_ratio <= 1.15)

        drift = abs(to_v(post["mean"], args.vdd) - vref)
        noise = max(to_v(pre["std"], args.vdd), to_v(post["std"], args.vdd)) \
            if pre["std"] else 0.001
        recover_ok = drift <= max(0.002, 3.0 * noise)

        if lift_ok and recover_ok:
            verdict = "PASS"
        elif lift_ok or recover_ok:
            verdict = "PARTIAL"

        print("\n===== 校验 =====")
        print("OPEN_PRE  基线 VREF = %.4f V" % vref)
        print("RESIST    实测 Vout = %.4f V   ΔV=+%.1f mV"
              % (got_vout, got_dv * 1000))
        print("          理论 Vout = %.4f V   ΔV=+%.1f mV"
              % (exp_vout, exp_dv * 1000))
        print("          ΔV 比值 = %.3f (0.85~1.15 为 PASS)" % dv_ratio)
        print("OPEN_POST 漂移 = %.2f mV (<=2mV 或 <=3*噪声 为 PASS)" % (drift * 1000))
        print("判定: %s" % verdict)

        summary = {
            "verdict": verdict,
            "config": {"port": args.port, "baud": args.baud,
                       "channel_index": args.channel,
                       "rtest_ohm": args.rtest, "rf_ohm": args.rf,
                       "vdd": args.vdd, "samples": args.samples},
            "open_pre": {"raw_mean": pre["mean"], "raw_std": pre["std"], "v": vref},
            "resist": {"raw_mean": res["mean"], "raw_std": res["std"],
                       "v": got_vout, "expected_v": exp_vout, "dv_ratio": dv_ratio},
            "open_post": {"raw_mean": post["mean"], "raw_std": post["std"],
                          "v": to_v(post["mean"], args.vdd), "drift_v": drift},
        }
    else:
        print("\n[FAIL] 有一段未采到数据，无法校验。请检查串口与接线。")
        summary = {"verdict": "FAIL", "error": "missing phase data"}

    summary_path = os.path.join(out_dir, "summary.json")
    with open(summary_path, "w") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)

    print("\n输出目录: %s" % out_dir)
    print("文件: OPEN_PRE.csv / RESIST.csv / OPEN_POST.csv / summary.json")
    ser.close()


if __name__ == "__main__":
    main()
