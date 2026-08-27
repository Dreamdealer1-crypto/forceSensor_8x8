# Project Traceability Rules

This project is run as an evidence-first hardware validation project. Every gate or order must keep a complete chain from instruction to firmware, capture script, raw data, analysis, report, and status ledger.

## Required Chain Per Order

Each order must have:

1. Order document under `执行/` or `方案/`.
2. Firmware source state recorded by Git commit hash.
3. Host tool source state recorded by Git commit hash.
4. Build and flash logs under `reports/logs/`.
5. Raw capture data under `data/`.
6. Analysis outputs generated from raw data, never hand-edited.
7. Human-readable result note under `reports/notes/`.
8. Supervisor-facing result under `reports/supervisor/`.
9. `docs/STATUS.md` updated with the final state.

## Data Policy

- Raw files are append-only evidence. Do not edit captured CSV/log files after capture.
- If metadata must be corrected, keep the original raw files and document the correction in the run manifest or result note.
- Derived outputs must be reproducible from raw files and versioned scripts.
- Each complete run should include a `MANIFEST.md` listing files, hashes, firmware mode, script names, and result.

## Git Policy

- Commit source, scripts, order docs, evidence manifests, result notes, and compact data needed to reproduce analysis.
- Do not commit build products from `build/`.
- Use one commit per coherent order result when practical.
- Commit messages should name the order and the evidence state, for example `Record ORDER-ARCH-01A direct TIA failure`.

## Current Evidence Index

| Order | Status | Dataset | Result note | Supervisor note |
|---|---|---|---|---|
| `ORDER-ARCH-01A` | `FAIL_WAITING_SUPERVISOR_REVIEW` | `data/arch_01a_direct_tia/20260815_033955_run01/` | `reports/notes/2026-08-15_order-arch-01a_direct-tia_result.md` | `reports/supervisor/2026-08-15_order-arch-01a_direct-tia-result.md` |
| `ORDER-ARCH-01A-R1` | `PAUSED_BLOCKED_WAITING_SUPERVISOR` | `data/arch_01a_r1/20260815_043342_run01/` | `reports/notes/2026-08-15_order-arch-01a-r1_paused-blocked.md` | `reports/supervisor/2026-08-15_order-arch-01a-r1_paused-blocked.md` |
| `ORDER-ARCH-01A-R2` | `PASS_WAITING_SUPERVISOR_REVIEW` | `data/arch_01a_r2/20260815_050457_run01/` | `reports/notes/2026-08-15_order-arch-01a-r2_software-chain-audit.md` | `reports/supervisor/2026-08-15_order-arch-01a-r2_software-chain-audit.md` |
| `ORDER-ARCH-01A-R3A` | `SUPERSEDED_BY_ADC01_AFTER_PARTIAL_OPEN_PRE` | `data/arch_01a_r3a/20260815_053726_run01/OPEN_PRE.csv` | pending | pending |
| `ORDER-ADC-01` | `PASS_WAITING_SUPERVISOR_REVIEW` | `data/adc_01/20260815_061128_run03/` | `reports/notes/2026-08-15_order-adc-01_pf6_polling_result.md` | `reports/supervisor/2026-08-15_order-adc-01_pf6-polling-result.md` |
| `ORDER-ADC-02` | `PASS_WAITING_SUPERVISOR_REVIEW` | `data/adc_02/20260815_061751_run01/` | `reports/notes/2026-08-15_order-adc-02_8rank_polling_result.md` | `reports/supervisor/2026-08-15_order-adc-02_8rank-polling-result.md` |
| `ORDER-ADC-03A` | `NOT_REPRODUCED_REVIEWED` | `data/adc_03a/20260815_062708_run02/` | `reports/notes/2026-08-15_order-adc-03a_dma_baseline_audit_result.md` | `reports/supervisor/2026-08-15_order-adc-03a_dma-baseline-audit-result.md` |
| `ORDER-ADC-03A code audit` | `CODE_AUDIT_DONE_FAULT_ISOLATED_TO_FIXTURE` | — | `reports/notes/2026-08-15_order-adc-03a_arch-vs-adc03a_code-audit.md` | — |

## Figure Policy

- Report figures should be SVG by default.
- Figures should include physical units, explicit thresholds, and concise titles.
- Derived figures must be reproducible from versioned raw data and analysis scripts.
