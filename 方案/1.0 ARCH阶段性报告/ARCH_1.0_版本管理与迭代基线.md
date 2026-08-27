# ARCH 1.0 版本管理与迭代基线

**日期：** 2026-08-19  
**项目：** 8x8 织物压力矩阵零电位 TIA 读出架构  
**基线版本：** ARCH 1.0  
**Git HEAD：** `cfd5bbd9f6256d0405fa752d1d75dabf6b6c3038`

---

## 1. 本次整理原则

本次整理遵循以下约束：

```text
不删除现有数据
不修改现有采集数据
不修改现有程序逻辑
不移动原始方案文档
只做复制归档、清单生成和版本基线说明
```

执行方案原件仍保留在：

```text
方案/
```

执行方案归档副本放在：

```text
执行/ARCH_1.0_ORDER执行归档/
```

ARCH 1.0 阶段报告与版本管理文件放在：

```text
方案/1.0 ARCH阶段性报告/
```

---

## 2. 执行方案归档

已复制归档的执行文件包括：

```text
执行/ARCH_1.0_ORDER执行归档/8x8_逐模块重建验证指南.md
执行/ARCH_1.0_ORDER执行归档/ORDER-ADC-01_PF6单通道Polling验证.md
执行/ARCH_1.0_ORDER执行归档/ORDER-ADC-02_八通道Scan_Polling无DMA验证.md
执行/ARCH_1.0_ORDER执行归档/ORDER-ADC-03A_DMA原始路径复现与审计.md
执行/ARCH_1.0_ORDER执行归档/ORDER-ARCH-01A-R3A_U1-U2交叉通道对照.md
执行/ARCH_1.0_ORDER执行归档/ORDER-ARCH-01A_直接TIA完整传递函数验证.md
执行/ARCH_1.0_ORDER执行归档/ORDER-REBUILD-H1_重建后传递函数验证.md
执行/ARCH_1.0_ORDER执行归档/ORDER-REBUILD-H2H3_ROW扫描复验与串扰实验.md
执行/ARCH_1.0_ORDER执行归档/ORDER-REBUILD-H4_真实传感器接入验证.md
```

说明：这些是 ARCH 1.0 阶段实际使用过的执行/验证单，后续新版本应复制为新的 `ARCH_1.1_ORDER执行归档` 或类似目录，不建议覆盖本目录。

---

## 3. 基线清单

本次生成了 SHA256 校验清单，用于后续判断文件是否被改动。

清单目录：

```text
方案/1.0 ARCH阶段性报告/manifests/
```

清单文件：

```text
ARCH_1.0_code_manifest.csv
ARCH_1.0_data_manifest.csv
ARCH_1.0_docs_manifest.csv
ARCH_1.0_figures_manifest.csv
ARCH_1.0_git_head.txt
ARCH_1.0_git_status_short.txt
```

含义：

| 清单 | 内容 |
|---|---|
| `ARCH_1.0_code_manifest.csv` | `firmware/` 与 `tools/` 下的程序文件 |
| `ARCH_1.0_data_manifest.csv` | H1/H2/H3/H4 关键数据目录 |
| `ARCH_1.0_docs_manifest.csv` | `方案/` 与 `执行/` 下的文档 |
| `ARCH_1.0_figures_manifest.csv` | H1/H2/H3/H4 汇报图件 |
| `ARCH_1.0_git_head.txt` | 当前 Git HEAD |
| `ARCH_1.0_git_status_short.txt` | 当前工作区状态 |

---

## 4. ARCH 1.0 冻结范围

### 4.1 程序基线

```text
firmware/
tools/capture_rebuild_h1.py
tools/analyze_rebuild_h1.py
tools/capture_rebuild_h2h3.py
tools/analyze_rebuild_h2h3.py
tools/capture_rebuild_h4.py
tools/analyze_rebuild_h4.py
```

### 4.2 数据基线

```text
data/rebuild_h1/
data/rebuild_h1_1/
data/rebuild_h2h3/
data/rebuild_h4/
data/rebuild_step13/
data/rebuild_step14/
```

### 4.3 图件基线

```text
reports/figures/rebuild_h1_1/
data/rebuild_h2h3/20260818_012046_run01/figures/
data/rebuild_h2h3/h3_abc_summary_20260818_015409/figures/
data/rebuild_h4/20260818_real_sensor_run01/figures/
```

### 4.4 文档基线

```text
方案/
执行/
```

---

## 5. 后续迭代建议目录结构

后续 ARCH 1.1 或 2.0 不建议覆盖 1.0 文件。推荐新建：

```text
方案/1.1 ARCH迭代方案/
执行/ARCH_1.1_ORDER执行归档/
data/rebuild_arch_1_1/
reports/figures/arch_1_1/
```

如果只是新增真实传感器测试批次，推荐：

```text
data/rebuild_h4/YYYYMMDD_real_sensor_run02/
```

如果修改了 Rf/Cf/VREF/ADC/4051 时序，应作为新架构版本，不应混入 ARCH 1.0 结论。

---

## 6. 只读保护建议

ARCH 1.0 的以下内容建议逻辑上视为只读：

```text
data/rebuild_h1/
data/rebuild_h2h3/
data/rebuild_h4/20260818_real_sensor_run01/
reports/figures/rebuild_h1_1/
方案/1.0 ARCH阶段性报告/
执行/ARCH_1.0_ORDER执行归档/
```

后续如需重新分析，建议输出到新目录，例如：

```text
data/reanalysis_arch_1_0/YYYYMMDD_<purpose>/
reports/figures/reanalysis_arch_1_0/YYYYMMDD_<purpose>/
```

---

## 7. 校验方式

后续如需检查某个文件是否与 ARCH 1.0 基线一致，可用：

```powershell
Get-FileHash -LiteralPath '<file>' -Algorithm SHA256
```

然后与对应 manifest 中的 `sha256` 比对。

如需重新生成某类清单，应另存为新文件，不覆盖当前清单：

```text
ARCH_1.1_code_manifest.csv
ARCH_1.1_data_manifest.csv
```

---

## 8. Git 状态说明

当前仓库中存在较多未跟踪数据、图件和脚本，这是本阶段实验开发自然产生的结果。由于用户要求不修改、不删除现有数据与程序，本次未进行清理、重置或删除。

建议后续正式版本管理流程：

1. 人工检查本报告与 manifest。
2. 确认需纳入 Git 的脚本、固件、文档。
3. 大体量原始数据可考虑使用外部归档或 Git LFS。
4. 为 ARCH 1.0 创建 tag，例如：

```powershell
git tag ARCH-1.0-validated
```

是否打 tag 或提交 commit，留给后续人工决策。

---

## 9. 版本边界

ARCH 1.0 冻结条件：

```text
Rf/Cf/VREF 未修改
ADC配置未修改
4051扫描时序未修改
ROW/COL硬件映射已确认
H1/H2/H3/H4 数据与图件已归档
```

触发新版本的条件：

```text
改变 Rf/Cf/VREF
改变 ADC scan rank / sampling time / DMA路径
改变 4051 settle time 或 ROW 驱动方式
改变传感器排布或排线方向
引入滤波、阈值、压力标定模型
扩展到 40x40 或其他规模阵列
```

ARCH 1.0 到此作为后续迭代的基线版本封存。
