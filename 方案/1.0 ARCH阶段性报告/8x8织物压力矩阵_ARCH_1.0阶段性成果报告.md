# 8x8织物压力矩阵 ARCH 1.0 阶段性成果报告

**项目路径：** `E:\算法学习\纤维矩阵压力传感器\Project\8x8resist_matrix`  
**报告日期：** 2026-08-19  
**当前阶段：** ARCH 1.0 阶段收口  
**当前代码版本：** `cfd5bbd9f6256d0405fa752d1d75dabf6b6c3038`  
**阶段结论：** ARCH 1.0 的 8x8 零电位 TIA 读出链路已完成从分立重建、标准电阻传递函数、ROW 扫描、2x2 串扰、到真实织物传感器接入的闭环验证。当前系统可作为后续 1.1/2.0 版本迭代的硬件与数据基线。

---

## 1. 最初方案需求

本阶段目标是为 8x8 织物压阻矩阵搭建一套可验证、可回溯、可扩展的电子读出架构，用于解决织物压力矩阵常见的行列串扰、弱信号读出、基线稳定性和真实传感器接入验证问题。

核心需求如下：

1. **8x8 阵列读出**
   - 支持 8 根 ROW 与 8 根 COL 的完整矩阵扫描。
   - 每个扫描周期输出完整 8x8 原始电压数据。

2. **零电位 TIA 读出架构**
   - 每个 COL 接入 MCP6002 的反相输入。
   - 通过运放虚地/近 VREF 节点降低非目标路径电位差。
   - 目标是抑制传统电阻矩阵扫描中的 ghosting。

3. **ROW 选择与静态偏置**
   - 使用 74HC4051 选择 ROW。
   - ROW 节点通过 100k 上拉到 VREF。
   - 选中 ROW 时由 4051 接到 GND，形成传感器电流路径。

4. **低风险逐模块验证**
   - 不直接接入真实织物传感器。
   - 先验证电源、VREF、TIA、ADC、4051、标准电阻传递函数。
   - 最后再接真实传感器。

5. **数据与图件可复现**
   - 所有串口原始数据保存为 CSV/log。
   - 所有分析脚本留存在 `tools/`。
   - 汇报图件输出 SVG，便于 PPT 和矢量软件修改。

---

## 2. ARCH 1.0 设计方案

### 2.1 硬件读出链路

ARCH 1.0 的核心链路为：

```text
传感器 ROWn
  -> 74HC4051 Yn 节点
  -> 被选中时接 GND

传感器 COLm
  -> MCP6002 反相输入 Pin2/Pin6
  -> TIA 输出 Pin1/Pin7
  -> STM32 ADC3 对应通道
```

### 2.2 信号基准

```text
3V3 约 3.29V
VREF 约 1.03V
TIA 非反相输入接 VREF
无输入时输出约 VREF
```

### 2.3 ROW/COL 映射

COL 到 TIA 输入：

| COL | TIA输入 | TIA输出 | ADC/串口 |
|---|---|---|---|
| COL0 | U1 Pin2 | U1 Pin1 | c0 |
| COL1 | U1 Pin6 | U1 Pin7 | c1 |
| COL2 | U2 Pin2 | U2 Pin1 | c2 |
| COL3 | U2 Pin6 | U2 Pin7 | c3 |
| COL4 | U3 Pin2 | U3 Pin1 | c4 |
| COL5 | U3 Pin6 | U3 Pin7 | c5 |
| COL6 | U4 Pin2 | U4 Pin1 | c6 |
| COL7 | U4 Pin6 | U4 Pin7 | c7 |

ROW 到 4051：

```text
ROW0~ROW7 -> 74HC4051 Y0~Y7
S0=PE14, S1=PE11, S2=PE9, E/INH=PG5
```

### 2.4 真实传感器物理显示坐标

H4 阶段确认真实传感器显示映射：

```text
右上角 = raw COL0 ROW0
右下角 = raw COL0 ROW7
```

因此展示层采用：

```text
raw ROW0 -> 物理上侧
raw ROW7 -> 物理下侧
raw COL0 -> 物理右侧
raw COL7 -> 物理左侧
transpose = false
```

最终 H4/ARCH-04 图件使用：

```powershell
python tools/analyze_rebuild_h4.py data/rebuild_h4/20260818_real_sensor_run01 --row-origin top --col-origin right --multi-points "1,2 4,6 6,2"
```

---

## 3. 固件实现

### 3.1 固件路径

```text
firmware/
firmware/Core/Src/main.c
firmware/Core/Inc/main.h
firmware/CMakeLists.txt
```

当前 H4 使用的固件模式为完整 8x8 ROW 扫描：

```text
T_SETTLE_US = 500
ADC_AVG_SCANS_PER_ROW = 16
ADC_DUMMY_SCANS_PER_ROW = 1
ARCH_01A_DIRECT_TIA_MODE = 0
ADC3_8RANK_DMA_BASELINE_AUDIT_MODE = 0
FRAME_PERIOD_MS = 0
```

串口输出格式：

```text
FRAME,<seq>,<timestamp_us>,1030
R0,c0,c1,c2,c3,c4,c5,c6,c7
...
R7,c0,c1,c2,c3,c4,c5,c6,c7
END
```

### 3.2 编译与烧录

构建：

```powershell
cmake -S .\firmware -B .\build\firmware -G Ninja -DCMAKE_BUILD_TYPE=Debug
cmake --build .\build\firmware
```

烧录：

```powershell
.\tools\flash-stm32.ps1 -Firmware .\build\firmware\resist_matrix_minimal.hex
```

当前烧录产物：

```text
build/firmware/resist_matrix_minimal.hex
```

---

## 4. PC端采集与分析脚本

### 4.1 H1 标准电阻传递函数

```text
tools/capture_rebuild_h1.py
tools/analyze_rebuild_h1.py
```

用途：

```text
采集标准电阻输入下的 TIA 输出
分析 Vout 与 1/R 的关系
输出传递函数、重复性、控制通道稳定性图件
```

### 4.2 H2/H3 ROW扫描与串扰

```text
tools/capture_rebuild_h2h3.py
tools/analyze_rebuild_h2h3.py
```

用途：

```text
H2：4051 ROW扫描空载基线
H3：2x2 标准电阻串扰实验 A/B/C
输出热图、局部响应柱状图、Kghost 图
```

### 4.3 H4 真实传感器

```text
tools/capture_rebuild_h4.py
tools/analyze_rebuild_h4.py
```

用途：

```text
实时显示 8x8 热图
保存 baseline / single_press / corner_press / multi_press 原始数据
按 baseline_mean 做差值热图
输出时间曲线、SNR、ARCH-04 汇总图
支持物理显示坐标映射
```

实时采集示例：

```powershell
python tools/capture_rebuild_h4.py --condition baseline --port COM7 --frames 500 --dataset-dir data/rebuild_h4/20260818_real_sensor_run01 --live
```

最终分析示例：

```powershell
python tools/analyze_rebuild_h4.py data/rebuild_h4/20260818_real_sensor_run01 --row-origin top --col-origin right --multi-points "1,2 4,6 6,2"
```

---

## 5. 验证路线与结果

### 5.1 H0/H13/H14 基础重建检查

重建过程中已完成：

```text
3V3 = 3.29V
VREF = 1.03V
U1~U4 静态输出约 1.02~1.03V
芯片不发热
4051 VCC = 3.29V
4051 Z/COM = 0V
4051 VEE = 0V
4051 E/INH = 3.29V 禁用态
ROW节点空载约 1.02V
```

8 路 ADC 基线在接入 U1~U4 与 4051 后仍保持约 VREF，说明前端接入未造成明显拉偏。

状态文档：

```text
方案/8x8_逐模块重建验证状态文档_v1.md
```

---

### 5.2 H1：标准电阻传递函数验证

目的：确认单通道 TIA 标准电阻输入下响应单调、连续、可重复。

数据目录：

```text
data/rebuild_h1/20260818_001616_run01/
```

关键结果：

```text
target_channel = c1
R² = 0.994024
Rf_eff = 8766.819 ohm
100k repeat diff = 0.224 mV
```

说明：

H1 采集时确认 U1 Pin1 / Pin7 到 PF4 / PF5 输出线曾接反，因此 U1A 响应记录在 c1。该批数据可作为传递函数和稳定性证据，但不作为原始 c0 映射 PASS 解释。后续接线已修复。

H1 图件：

```text
reports/figures/rebuild_h1_1/ppt_run01/00_ppt_summary_16x9.svg
reports/figures/rebuild_h1_1/ppt_run01/01_vout_vs_r_log_ieee.svg
reports/figures/rebuild_h1_1/ppt_run01/02_delta_v_vs_conductance_fit.svg
reports/figures/rebuild_h1_1/ppt_run01/03_c0_c1_mapping_diagnostic.svg
reports/figures/rebuild_h1_1/ppt_run01/04_100k_repeatability.svg
reports/figures/rebuild_h1_1/ppt_run01/05_c1_stitched_time_trace.svg
reports/figures/rebuild_h1_1/ppt_run01/06_control_channel_drift_heatmap.svg
```

结论：

标准电阻输入下 TIA 链路具有明确电导响应关系，100k 重复性很好。H1 支持后续矩阵扫描与真实传感器接入。

---

### 5.3 H2：ROW扫描空载复验

目的：确认 4051 在固件控制下逐行选通时，不会引入 ROW/COL 异常偏移或寄生路径。

数据目录：

```text
data/rebuild_h2h3/20260818_012046_run01/
```

关键结果：

```text
STATUS = PASS
frames = 2
row_records = 16
point_count = 128
64-point range = 1025.781mV ~ 1038.482mV
mean = 1032.635mV
repeat_max_abs_diff = 6.426mV
anomaly_count = 0
```

H2 图件：

```text
data/rebuild_h2h3/20260818_012046_run01/figures/h2_ppt_summary_16x9.svg
data/rebuild_h2h3/20260818_012046_run01/figures/h2_row_scan_heatmap.svg
data/rebuild_h2h3/20260818_012046_run01/figures/h2_column_traces.svg
data/rebuild_h2h3/20260818_012046_run01/figures/h2_uniformity_repeatability.svg
```

结论：

4051 ROW0~ROW7 扫描时，全部 ROW-COL 点维持在 VREF 附近，无异常选通偏移。H2 通过。

---

### 5.4 H3：2x2 标准电阻串扰实验

目的：用标准 47k 电阻在 2x2 子阵中验证零电位 TIA 架构对 ghosting 的抑制效果。

最终子阵：

```text
ROW2 / ROW3 x COL4 / COL5
COL4 = U3A / c4
COL5 = U3B / c5
```

数据目录：

```text
实验A：data/rebuild_h2h3/20260818_014709_expA_run01/
实验B：data/rebuild_h2h3/20260818_015023_expB_run01/
实验C：data/rebuild_h2h3/20260818_015409_expC_run01/
汇总：data/rebuild_h2h3/h3_abc_summary_20260818_015409/
```

实验A：单像素

```text
ROW2-c4 = 1252.320mV
ROW2-c5 = 1032.168mV
ROW3-c4 = 1030.862mV
ROW3-c5 = 1030.866mV
target_delta = 220.174mV
Kghost_local = 0.583%
STATUS = PASS
```

实验B：双对角

```text
ROW2-c4 = 1253.010mV
ROW2-c5 = 1033.835mV
ROW3-c4 = 1030.898mV
ROW3-c5 = 1254.265mV
Kghost_c4 = 0.743%
Kghost_c5 = 0.586%
STATUS = PASS
```

实验C：满 2x2

```text
ROW2-c4 = 1214.394mV
ROW2-c5 = 1217.387mV
ROW3-c4 = 1188.217mV
ROW3-c5 = 1190.829mV
四目标最小Delta = 155.627mV
STATUS = PASS
```

H3 汇总图件：

```text
data/rebuild_h2h3/h3_abc_summary_20260818_015409/figures/h3_abc_heatmaps.svg
data/rebuild_h2h3/h3_abc_summary_20260818_015409/figures/h3_abc_local_response.svg
data/rebuild_h2h3/h3_abc_summary_20260818_015409/figures/h3_abc_ghost_coefficient.svg
```

结论：

2x2 子阵中目标点定位正确，ghost 系数均低于 1%，显著低于 5% 验收判据。H3 证明零电位 TIA 架构在标准电阻层面具备有效串扰抑制能力。

---

### 5.5 H4：真实 8x8 织物传感器接入验证

目的：确认真实织物传感器接入后，空载基线、单点按压、四角按压、多点按压均具有可解释响应。

数据目录：

```text
data/rebuild_h4/20260818_real_sensor_run01/
```

采集内容：

```text
baseline.csv：500帧
single_press.csv：180帧
corner_press.csv：360帧
multi_press.csv：180帧
```

最终显示映射：

```text
row_origin = top
col_origin = right
transpose = false
```

基线结果：

```text
frame_rate = 15.732Hz
baseline mean range = 1029.486mV ~ 1040.863mV
baseline max std = 4.151mV
all_mean_in_1020_1060 = true
all_std_lt_10 = true
```

单点按压：

```text
raw peak = R4C4
display peak = X3,Y4
peak_delta = 890.461mV
SNR = 228.9
```

四角按压：

```text
raw peak = R6C0
display peak = X7,Y6
peak_delta = 884.967mV
SNR = 273.7
```

多点补测：

用户给定目标点：

```text
(1,2), (4,6), (6,2)
```

已知点响应：

```text
R1C2 -> display X5,Y1：Delta = 867.573mV，SNR = 536.9
R4C6 -> display X1,Y4：Delta = 13.942mV，SNR = 8.3
R6C2 -> display X5,Y6：Delta = 234.869mV，SNR = 140.1
```

实际峰值排名：

```text
R6C1：Delta = 889.678mV
R3C6：Delta = 878.151mV
R1C2：Delta = 867.573mV
R6C2：Delta = 234.869mV
```

解释：

多点补测显示至少三个独立响应区域。部分强峰落在用户标注点的相邻像素，说明手指按压区域、织物触点面积和物理坐标中心存在一格以内偏移。作为 PPT 展示时建议同时标注 `intended press point` 与 `actual peak pixel`。

H4 图件：

```text
data/rebuild_h4/20260818_real_sensor_run01/figures/baseline_heatmap.svg
data/rebuild_h4/20260818_real_sensor_run01/figures/baseline_std_heatmap.svg
data/rebuild_h4/20260818_real_sensor_run01/figures/single_press_delta_heatmap.svg
data/rebuild_h4/20260818_real_sensor_run01/figures/single_press_timeseries.svg
data/rebuild_h4/20260818_real_sensor_run01/figures/corner_press_delta_grid.svg
data/rebuild_h4/20260818_real_sensor_run01/figures/multi_press_known_points_delta_heatmap.svg
data/rebuild_h4/20260818_real_sensor_run01/figures/multi_press_known_points_timeseries.svg
data/rebuild_h4/20260818_real_sensor_run01/figures/h4_arch04_summary.svg
```

结论：

真实织物传感器接入后，空载基线稳定，按压响应幅度大、SNR 高，单点与多点均可观察到明确空间响应。H4 已达到 `READY_FOR_H4_REVIEW`，可作为 ARCH 1.0 的真实传感器展示素材。

---

## 6. 阶段性总体验收结论

ARCH 1.0 阶段完成了从硬件重建到真实传感器接入的完整闭环：

```text
H1：标准电阻传递函数成立，R² = 0.994，100k重复差 = 0.224mV
H2：ROW扫描空载稳定，128点全在 1025.781~1038.482mV
H3：2x2串扰验证通过，Kghost < 1%
H4：真实传感器接入后，基线稳定，按压响应显著，单点峰值Delta约 890mV
```

因此，ARCH 1.0 可定义为：

```text
8x8 zero-potential TIA readout architecture, validated with standard resistors and real fabric sensor.
```

中文表述：

```text
8x8 零电位 TIA 织物压力矩阵读出架构，已通过标准电阻与真实织物传感器双重验证。
```

---

## 7. 当前已知问题与边界

1. **H1 早期采集存在 c0/c1 输出线接反**
   - 已在文档中记录。
   - H1 图件使用 c1 作为实际响应通道。
   - 后续接线已修正，H3/H4 映射正常。

2. **H4 多点按压存在相邻像素偏移**
   - 真实织物传感器的按压面积覆盖多个像素。
   - 部分 intended point 的 actual peak 落在相邻点。
   - 这不是电路失效，更像传感器空间分辨率、手指接触面积和物理坐标标定问题。

3. **当前未进入 H5 参数优化**
   - 未修改 Rf/Cf/VREF。
   - 未做滤波、阈值、压力标定。
   - 当前所有 raw 数据保留原始电压。

4. **40x40 或更大阵列尚未设计**
   - ARCH 1.0 只验证 8x8。
   - 40x40 需要重新评估 ROW/COL 扩展、扫描速度、模拟开关漏电、布线寄生和算法显示。

---

## 8. 后续迭代建议

### 8.1 ARCH 1.1：显示与映射标定

目标：

```text
建立 raw ROW/COL 到 physical X/Y 的正式标定表
支持任意翻转、转置、重排
在图中同时显示 intended press point 与 actual peak
```

建议输出：

```text
mapping_config.json
calibrated_heatmap_renderer.py
ARCH-04 PPT最终图件
```

### 8.2 ARCH 1.2：真实传感器动态指标

目标：

```text
量化响应时间、恢复时间、滞后、漂移、重复按压稳定性
```

建议实验：

```text
固定砝码或标准压力头
同一点重复按压 N 次
不同压力等级曲线
```

### 8.3 ARCH 2.0：参数优化

目标：

```text
根据真实传感器阻值范围优化 Rf/Cf/VREF
提升动态范围
降低噪声
为更大阵列做扫描速度与串扰优化
```

注意：

```text
不得直接在 ARCH 1.0 数据基础上修改 Rf/Cf 后混用结论。
参数优化应作为新版本重新验证 H1~H4。
```

---

## 9. 关键文件索引

### 9.1 方案与状态文档

```text
方案/8x8_织物压力矩阵_零电位TIA_开发与验收方案_v1.0.md
方案/8x8_逐模块重建验证指南.md
方案/8x8_逐模块重建验证状态文档_v1.md
方案/ORDER-REBUILD-H1_重建后传递函数验证.md
方案/ORDER-REBUILD-H2H3_ROW扫描复验与串扰实验.md
方案/ORDER-REBUILD-H4_真实传感器接入验证.md
```

### 9.2 固件

```text
firmware/Core/Src/main.c
firmware/Core/Inc/main.h
firmware/CMakeLists.txt
build/firmware/resist_matrix_minimal.hex
```

### 9.3 采集与分析脚本

```text
tools/capture_rebuild_h1.py
tools/analyze_rebuild_h1.py
tools/capture_rebuild_h2h3.py
tools/analyze_rebuild_h2h3.py
tools/capture_rebuild_h4.py
tools/analyze_rebuild_h4.py
tools/flash-stm32.ps1
tools/check-stm32-tools.ps1
```

### 9.4 核心数据目录

```text
data/rebuild_h1/20260818_001616_run01/
data/rebuild_h2h3/20260818_012046_run01/
data/rebuild_h2h3/20260818_014709_expA_run01/
data/rebuild_h2h3/20260818_015023_expB_run01/
data/rebuild_h2h3/20260818_015409_expC_run01/
data/rebuild_h2h3/h3_abc_summary_20260818_015409/
data/rebuild_h4/20260818_real_sensor_run01/
```

### 9.5 汇报图件

H1：

```text
reports/figures/rebuild_h1_1/ppt_run01/
```

H2：

```text
data/rebuild_h2h3/20260818_012046_run01/figures/
```

H3：

```text
data/rebuild_h2h3/h3_abc_summary_20260818_015409/figures/
```

H4：

```text
data/rebuild_h4/20260818_real_sensor_run01/figures/
```

---

## 10. ARCH 1.0 版本冻结说明

从本报告开始，ARCH 1.0 的结论基于以下前提冻结：

```text
Rf/Cf/VREF 未修改
ADC 配置未修改
4051 时序未修改
固件为完整 8x8 ROW 扫描 raw 输出
显示层采用 row_origin=top, col_origin=right, transpose=false
```

任何后续修改以下内容，应作为新版本重新验证：

```text
Rf/Cf/VREF
ROW/COL硬件接线
ADC采样时间/扫描顺序/DMA路径
4051 settle time
软件滤波/阈值/基线扣除策略
传感器结构或排线顺序
```

ARCH 1.0 到此阶段性收口。
