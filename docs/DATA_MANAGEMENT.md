# Data Management

## Directory Layout

| Directory | Purpose |
|---|---|
| `data/templates/` | Empty measurement templates |
| `data/raw/` | Raw serial logs, instrument notes, unmodified source data |
| `data/csv/` | Parsed or manually entered CSV datasets |
| `data/analysis/` | Analysis outputs and intermediate tables |
| `data/arch_01a_direct_tia/<run>/` | ORDER-ARCH-01A complete raw, metadata, analysis, plots, and manifest |
| `data/arch_01a_r1/<run>/` | ORDER-ARCH-01A-R1 single-condition captures, summary, SVG plots, and manifest |
| `data/arch_01a_r2/<run>/` | ORDER-ARCH-01A-R2 reader audit logs, statistics, session audit, and manifest |
| `reports/figures/` | Figures intended for reports |
| `reports/notes/` | Short experiment notes and supervisor-facing summaries |

## File Naming

Use:

```text
YYYY-MM-DD_gate_<gate>_<experiment>_<sample-or-condition>_runNN.<ext>
```

Examples:

```text
2026-08-12_gate_h0_static_power_run01.csv
2026-08-12_gate_h1_transfer_r10k_run01.csv
2026-08-12_gate_h1_transfer_curve_run01.png
```

## Evidence Rules

- Raw data is not edited after capture.
- Derived CSV files and figures must be reproducible from source data.
- Report figures go under `reports/figures/` and keep the same gate/run identifiers as their source data.
- Each supervisor review must reference exact evidence file paths.
- Each complete order run should include `metadata.json`, raw CSV, analysis outputs, plots, logs, a result note, a supervisor note, and a `MANIFEST.md` with hashes when practical.
- If a host script crashes after some conditions are saved, keep the partial files and resume into the same dataset directory only when the saved condition CSVs are still valid and documented.
- Report-ready plots should be generated as SVG unless a downstream tool explicitly requires raster output.

## Current Complete Run

| Run | Status | Directory |
|---|---|---|
| `ORDER-ARCH-01A / 20260815_033955_run01` | `FAIL_WAITING_SUPERVISOR_REVIEW` | `data/arch_01a_direct_tia/20260815_033955_run01/` |
| `ORDER-ARCH-01A-R2 / 20260815_050457_run01` | `PASS_WAITING_SUPERVISOR_REVIEW` | `data/arch_01a_r2/20260815_050457_run01/` |
| `ORDER-ADC-01 / 20260815_061128_run03` | `PASS_WAITING_SUPERVISOR_REVIEW` | `data/adc_01/20260815_061128_run03/` |
| `ORDER-ADC-02 / 20260815_061751_run01` | `PASS_WAITING_SUPERVISOR_REVIEW` | `data/adc_02/20260815_061751_run01/` |
| `ORDER-ADC-03A / 20260815_062708_run02` | `NOT_REPRODUCED_REVIEWED` | `data/adc_03a/20260815_062708_run02/` |
