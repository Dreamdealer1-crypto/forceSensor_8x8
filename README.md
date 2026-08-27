# forceSensor_8x8

8x8 textile piezoresistive force sensor project for matrix readout, force-ramp capture, calibration, and receptive-field analysis.

本项目面向织物压阻矩阵压力传感器实验：完成 8x8 零电位 TIA 读出链、连续压力加载采集、压力-ADC 响应分析、邻域响应与感受野可视化。

## Repository Layout

```text
firmware/        STM32H743 8x8 ROW 扫描固件
sensor/          Arduino Mega / HX711 称重模块验证代码
tools/           串口采集、实时可视化、数据分析脚本
tools/phase2/    PHASE 2.0 连续加载与感受野分析工具
PCB/             电路与结构说明
docs/            状态、追溯与数据管理文档
方案/            实验方案、理论说明与阶段报告
reports/figures/ 精选可汇报图件，不包含原始大数据
```

## Data Policy

Raw experiment data is intentionally excluded from Git by default.

原始采集数据通常包含大量 CSV / Excel / 串口日志，默认不提交到仓库。建议按实验日期归档在本地 `data/`，或使用外部数据盘/云盘保存。仓库中只保留可复现脚本、文档和少量精选报告图件。

## Firmware Output

The 8x8 matrix firmware serial stream uses the H4 frame format:

```text
FRAME,<seq>,<timestamp_us>,1030
R0,c0,c1,...,c7
...
R7,c0,...,c7
END
```

ADC data is stored as raw voltage/ADC response first; baseline subtraction, filtering, conductance conversion, calibration, and receptive-field calculations are performed in analysis scripts.

## Force-Ramp Capture

Continuous force-ramp experiments are collected with:

```powershell
python tools\phase2\capture_force_ramp.py `
  --grid-row 4 --grid-col 3 `
  --ramp-rate 0.2 `
  --port COM7 `
  --dataset-dir data\phase2\force_ramp\R4C3_40N `
  --live-plot
```

The script creates a new timestamped run directory on every capture. Start/stop is controlled from the terminal, so mechanical force data and sensor data can be aligned afterwards.

## Analysis

Typical PHASE 2.0 analysis scripts:

```powershell
python tools\phase2\analyze_force_ramp_run1_r4c3_v2.py
python tools\phase2\make_e2_receptive_field_figures.py
```

Generated outputs include raw ADC curves, filtered force-response curves, F-ADC calibration plots, 2D/3D heatmaps, 3x3 neighbor trends, and receptive-field summary figures.

## Python Environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Hardware Notes

- Matrix readout target: STM32H743 + 8x8 row-scan architecture.
- Auxiliary load-cell validation: Arduino Mega + HX711 / serial weighing module.
- PHASE 2.0 loading plan: compression instrument or XYZ platform drives a 4 mm circular indenter onto a target taxel, with continuous loading rate such as 0.2 N/s.

## License

No license has been selected yet. Add a license before public reuse or distribution.
