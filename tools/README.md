# Local STM32 Tools

This folder adapts the project to the current Windows machine.

Detected tools:

- `STM32_Programmer_CLI`: `D:\STM32CubeCLT_1.22.0\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe`
- `arm-none-eabi-gcc`: `D:\STM32CubeCLT_1.22.0\GNU-tools-for-STM32\bin\arm-none-eabi-gcc.exe`
- `cmake`: `D:\STM32CubeCLT_1.22.0\CMake\bin\cmake.exe`
- `ninja`: `D:\STM32CubeCLT_1.22.0\Ninja\bin\ninja.exe`
- `make`: `D:\STM32CubeCLT_1.22.0\Make\bin\make.exe`

Check the local setup:

```powershell
.\tools\check-stm32-tools.ps1
```

Flash firmware through the NUCLEO-H743ZI2 onboard ST-LINK:

```powershell
.\tools\flash-stm32.ps1 -Firmware .\build\firmware.hex
```

For a raw binary, the script writes to flash base address `0x08000000` by default:

```powershell
.\tools\flash-stm32.ps1 -Firmware .\build\firmware.bin
```

The local path override lives in `stm32-tools.local.ps1`.
Use `stm32-tools.local.example.ps1` as the versioned reference when setting up another machine.

## ORDER-ARCH-01A Direct TIA Tools

Capture:

```powershell
python .\tools\capture_arch_01a_direct_tia.py --port COM7 --baud 115200 --run run01
```

Resume a partially completed run:

```powershell
python .\tools\capture_arch_01a_direct_tia.py --port COM7 --baud 115200 --dataset-dir .\data\arch_01a_direct_tia\<run> --start-at 10k
```

Analyze:

```powershell
python .\tools\analyze_arch_01a_direct_tia.py .\data\arch_01a_direct_tia\<run>
```

Expected dataset contents:

- `metadata.json`
- one CSV per condition
- `raw_all_conditions.csv`
- `analysis_summary.csv`
- `control_channels_summary.csv`
- `fit_results.json`
- `plots/`
- `MANIFEST.md`

## ORDER-ARCH-01A-R1 Single-Condition Tools

R1 deliberately captures one resistor condition per process. Do not use the automatic 14-condition capture script for this order.

First condition example:

```powershell
python .\tools\capture_arch_01a_r1_single_condition.py --condition 100k --r-ohm 97940 --port COM7
```

Subsequent conditions must reuse the same dataset directory printed by the first run:

```powershell
python .\tools\capture_arch_01a_r1_single_condition.py --condition 47k --r-ohm 46000 --dataset-dir .\data\arch_01a_r1\<run> --port COM7
```

Analyze after all eight single-condition runs:

```powershell
python .\tools\analyze_arch_01a_r1.py .\data\arch_01a_r1\<run>
```

R1 plot outputs are SVG files suitable for reports:

- `01_r1_deltaV_vs_inverseR.svg`
- `02_r1_open_recovery.svg`
- `03_r1_repeatability.svg`
- `04_r1_residual_vs_R.svg`
- `05_r1_col0_protocol_trace.svg`
- `06_r1_control_channel_std.svg`

## ORDER-ARCH-01A-R2 Software Chain Audit

R2 compares three reader styles without changing hardware:

```powershell
python .\tools\audit_arch_01a_r2_readers.py --port COM7 --samples 300 --run run01
```

Outputs:

- `data/arch_01a_r2/<run>/raw_terminal_reader.log`
- `data/arch_01a_r2/<run>/r1_preview_reader.log`
- `data/arch_01a_r2/<run>/r1_capture_reader.log`
- `data/arch_01a_r2/<run>/reader_stats.csv`
- `data/arch_01a_r2/<run>/session_seq_audit.csv`
- `data/arch_01a_r2/<run>/audit_result.json`

## ORDER-ARCH-01A-R3A U2/COL2 Cross-Channel Capture

R3A keeps the session-aware `ARCH_01A_DIRECT_TIA` firmware and moves the direct Rtest path to U2A:

```text
TEST_U2_A = U2 Pin2
TEST_U2_B = GND
target ADC channel = COL2 / c2_raw
```

Run:

```powershell
python .\tools\capture_arch_01a_r3a_u2.py --port COM7 --run run01 --r100-ohm 97710 --r47-ohm 45960 --r22-ohm 22320 --r10-ohm 9920
```

The script prompts the sequence `OPEN_PRE -> 100k -> OPEN_1 -> 47k -> OPEN_2 -> 22k -> OPEN_3 -> 10k -> OPEN_POST`, saves all 8 raw channels, and emits SVG report figures under `data/arch_01a_r3a/<run>/plots/`.
