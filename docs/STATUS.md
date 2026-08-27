# 8x8 Resist Matrix Project Status

## Current Supervisor Order

- Order ID: `ORDER-ADC-03A`
- Source: User / Supervisor
- Received: `2026-08-15`
- Instruction: Reproduce and audit the original 8-rank ADC3 DMA NORMAL path without applying DMA/cache fixes while fixed hardware remains U2 Pin2 -> 100k -> GND.
- Current status: `NOT_REPRODUCED_REVIEWED_FAULT_ISOLATED_TO_TEST_FIXTURE`

## Active Restrictions

- Do not connect or test the real fabric sensor unless a new explicit ORDER allows it.
- Do not make or tune heatmaps unless a new explicit ORDER allows it.
- Do not calculate or display pressure values unless calibration evidence exists and a new explicit ORDER allows it.
- Do not cross any Gate without user/supervisor evidence acceptance.

## Execution Rules

- Main firmware and project files are version controlled with Git.
- Do not overwrite previous accepted firmware versions directly.
- Keep supervisor orders, execution status, evidence files, and results in sync.
- Every execution state change, measurement result, abnormal condition, blocker, and request to enter the next step must include a prepared reply to `@监工`.
- Supervisor replies must be saved under `reports/supervisor/` with exact evidence paths.
- Do not connect the real 8x8 fabric sensor until supervisor approval after required gates.
- Do not implement scanning firmware before H0 measurements are reviewed.
- Every result requires evidence review before the next ORDER.
- No evidence means no Gate crossing.

## Gate Status

| Gate | Status | Evidence | Notes |
|---|---|---|---|
| H0 power/static operating point | `PASS_USER_REPORTED` | `data/csv/2026-08-12_gate_h0_static_power_run01.csv`, `data/csv/2026-08-12_gate_h0_observations_run01.csv` | 3V3/VREF numeric; U1-U4 pins qualitative normal; scope check not reported |
| ORDER-002 minimal firmware | `READY_FOR_SUPERVISOR_REVIEW` | `firmware/`, `reports/logs/2026-08-12_order-002_build.log`, `reports/logs/2026-08-12_order-002_flash.log`, `data/raw/2026-08-12_order-002_raw_uart_5frames_run01.log`, `data/analysis/2026-08-12_order-002_unloaded_adc_stats_run01.csv` | Built, flashed, 5 RAW frames captured |
| ORDER-002A slow ROW test | `PASS_USER_REPORTED_WITH_OBSERVATION` | `reports/logs/2026-08-12_order-002a_build.log`, `reports/logs/2026-08-12_order-002a_flash.log`, `data/raw/2026-08-12_order-002a_row_uart_run01.log`, `data/csv/2026-08-12_order-002a_row_voltage_run01.csv` | Selected rows 0 V; unselected rows mostly about 1 V, occasional about 1.3 V |
| ORDER-003 standard resistor transfer | `FAIL_REWORK_REQUIRED` | `data/analysis/2026-08-13_order-003_transfer_diagnostic_run01.csv`, `reports/notes/2026-08-13_order-003_transfer_rework_run01.md` | 1M replaced by 1.5M; 10k/22k have 99 samples; transfer response is flat |
| ORDER-003A FAST-A TIA bypass debug | `PASS_TIA_ADC_RESPONDS` | `data/raw/2026-08-13_order-003a_fast_a_u1pin2_10k_gnd_run01.log`, `data/analysis/2026-08-13_order-003a_fast_a_u1pin2_10k_gnd_stats_run01.csv` | 10k from U1 Pin2/COL0 negative input to GND; COL0 rises to about 1.924 V |
| ORDER-003A FAST-B ROW0-COL0 debug | `PASS_RESPONSE_OBSERVED_AFTER_FIX` | `data/raw/2026-08-13_order-003a_fast_b_row0_10k_col0_run04_after_fix.log`, `data/analysis/2026-08-13_order-003a_fast_b_row0_10k_col0_stats_run04_after_fix.csv`, `reports/notes/2026-08-13_order-003a_fast_b_result_run04_after_fix.md` | After fix, ROW0->10k->COL0 raises COL0 to about 1.925 V |
| ORDER-003B power-off continuity check | `WAITING_USER_MEASUREMENT` | `reports/notes/2026-08-13_order-003b_poweroff_continuity_check.md`, `data/templates/order_003b_poweroff_continuity.csv` | Check only physical COL0 contact to U1 Pin2 and physical ROW0 contact to 74HC4051 Y0 |
| ORDER-003E quick 4-point transfer | `FAIL_NONLINEAR_HIGH_RESISTANCE_DROPOUT` | `reports/notes/2026-08-13_order-003e_quick_transfer_final.md`, `data/analysis/2026-08-13_order-003e_quick_transfer_summary_run01_order003e.csv`, `data/analysis/2026-08-13_order-003e_quick_transfer_fit_run01_order003e.csv` | 10k/22k high, 47k/100k near VREF; R2=0.690449 |
| ORDER-DEMO-001 press demo | `ARCHIVED_REPORT_ACCELERATION` | `reports/notes/2026-08-13_order-demo-001_run03_manual_result.md`, `data/analysis/2026-08-13_order-demo-001_summary_run03_manual.csv`, `reports/figures/2026-08-13_order-demo-001_run03_manual/` | Report acceleration artifact; not accepted as next Gate basis |
| Live single-point pressure heatmap | `ARCHIVED_REPORT_ACCELERATION` | `tools/live_pressure_heatmap.py`, `tools/run-live-pressure-heatmap.ps1`, `reports/notes/2026-08-13_order-live-pressure_v3_reoptimize.md`, `reports/figures/2026-08-13_order-live-pressure_preview/peak_preview_v3_reoptimized.png`, `data/csv/2026-08-13_order-live-pressure_run01_live_pressure_summary.csv` | Report acceleration artifact; poor effect; not accepted as next Gate basis |
| Gate discipline restored | `WAITING_NEXT_ORDER` | `reports/notes/2026-08-13_return_to_gate_discipline.md`, `reports/supervisor/2026-08-13_return-to-gate-discipline.md` | User/supervisor evidence review required before any next Gate |
| ORDER-ARCH-01A direct TIA transfer | `FAIL_WAITING_SUPERVISOR_REVIEW` | `data/arch_01a_direct_tia/20260815_033955_run01/`, `reports/notes/2026-08-15_order-arch-01a_direct-tia_result.md`, `reports/supervisor/2026-08-15_order-arch-01a_direct-tia-result.md` | R2=0.774574; first 22k drops to VREF; repeat points inconsistent; OPEN_POST high/noisy |
| ORDER-ARCH-01A-R1 resistor-change protocol retest | `PAUSED_BLOCKED_WAITING_SUPERVISOR` | `data/arch_01a_r1/20260815_043342_run01/`, `reports/supervisor/2026-08-15_order-arch-01a-r1_paused-blocked.md` | 100k partial run invalid; exact root cause not identified; user fatigue, do not continue repeated manual retry |
| ORDER-ARCH-01A-R2 software acquisition-chain audit | `PASS_WAITING_SUPERVISOR_REVIEW` | `data/arch_01a_r2/20260815_050457_run01/`, `reports/supervisor/2026-08-15_order-arch-01a-r2_software-chain-audit.md` | Three readers agree within 0.323 mV; session 455307244; no seq gaps; no old reader process found |
| ORDER-ARCH-01A-R3A U1/U2 cross-channel comparison | `SUPERSEDED_BY_ADC01_AFTER_PARTIAL_OPEN_PRE` | `tools/capture_arch_01a_r3a_u2.py`, `方案/ORDER-ARCH-01A-R3A_U1-U2交叉通道对照.md`, `data/arch_01a_r3a/20260815_053726_run01/OPEN_PRE.csv` | Partial OPEN_PRE captured; 100k preview stayed near OPEN; user/supervisor switched to ORDER-ADC-01 |
| ORDER-ADC-01 PF6 single-channel polling | `PASS_WAITING_SUPERVISOR_REVIEW` | `data/adc_01/20260815_061128_run03/`, `reports/supervisor/2026-08-15_order-adc-01_pf6-polling-result.md`, `reports/logs/2026-08-15_order-adc-01_build.log`, `reports/logs/2026-08-15_order-adc-01_flash.log`, `reports/logs/2026-08-15_order-adc-01_capture.log` | PF6/ADC3_INP8 polling reads 1.143310 V; Rank1=8, PCSEL_CH8=1, DIFSEL_CH8=0, DMA=0 |
| ORDER-ADC-02 8-rank scan polling | `PASS_WAITING_SUPERVISOR_REVIEW` | `data/adc_02/20260815_061751_run01/`, `reports/supervisor/2026-08-15_order-adc-02_8rank-polling-result.md`, `reports/logs/2026-08-15_order-adc-02_build.log`, `reports/logs/2026-08-15_order-adc-02_flash.log`, `reports/logs/2026-08-15_order-adc-02_capture.log` | Rank3/c2 PF6 reads 1.143634 V; runtime SQR order correct; all PCSEL bits set; all DIFSEL bits single-ended; DMA=0 |
| ORDER-ADC-03A DMA baseline audit | `NOT_REPRODUCED_WAITING_SUPERVISOR_REVIEW` | `data/adc_03a/20260815_062708_run02/`, `reports/supervisor/2026-08-15_order-adc-03a_dma-baseline-audit-result.md`, `reports/notes/2026-08-15_order-adc-03a_arch-vs-adc03a_code-audit.md`, `reports/logs/2026-08-15_order-adc-03a_build.log`, `reports/logs/2026-08-15_order-adc-03a_flash.log`, `reports/logs/2026-08-15_order-adc-03a_capture.log` | DMA NORMAL baseline with callback wait reads rank3/c2 1.143236 V; read_before_tc=0/1000; callback_seen=1000/1000; NDTR after start 8 and at read 0; no OVR/DMA errors |
| H1 transfer function | `BLOCKED_ATTRIBUTED_TO_TEST_FIXTURE` | `reports/notes/2026-08-15_order-adc-03a_arch-vs-adc03a_code-audit.md` | TIA/ADC/DMA chain verified normal; prior 47k/100k dropout attributed to breadboard contact instability; requires stable-fixture retest |
| H2 ROW scan verification | `BLOCKED` | - | Requires supervisor instruction |
| H3 2x2 crosstalk | `BLOCKED` | - | Requires H1/H2 PASS |
| H4 real 8x8 sensor | `BLOCKED` | - | Real sensor must not be connected |

## Latest Actions

| Date | Actor | Action | Result |
|---|---|---|---|
| 2026-08-12 | Codex | Checked local STM32 tools | `STM32_Programmer_CLI`, `arm-none-eabi-gcc`, `cmake`, `ninja`, `make` found |
| 2026-08-12 | Codex | Initialized Git repository | Ready for versioned development |
| 2026-08-12 | Codex | Recorded `ORDER-001` | Work limited to H0 static measurements |
| 2026-08-12 | Codex | Recorded `ORDER-001A` | Added required H0 submission fields |
| 2026-08-12 | Codex | Added supervisor reply rule | Every status/result/blocker must prepare a `@监工` reply |
| 2026-08-12 | User | Reported H0 measurements | 3V3=3.3 V, VREF=1.03 V, U1-U4 Pin3/Pin5/Pin1/Pin7 all normal, H0 pass |
| 2026-08-12 | Codex | Prepared supervisor reply for H0 run01 | `reports/supervisor/2026-08-12_gate-h0_static-result_run01.md` |
| 2026-08-12 | Supervisor | Issued `ORDER-002` | Minimal STM32 firmware scope only |
| 2026-08-12 | Codex | Implemented ORDER-002 firmware | `.ioc`, ADC3 DMA, USART3 RAW output, T_SETTLE=500 us |
| 2026-08-12 | Codex | Built and flashed ORDER-002 firmware | Build PASS; flash verified successfully |
| 2026-08-12 | Codex | Captured ORDER-002 RAW UART data | 5 frames captured from COM7 |
| 2026-08-12 | Supervisor | Issued `ORDER-002A` | Add slow ROW test mode |
| 2026-08-12 | Codex | Implemented ORDER-002A ROW test mode | 2 s ROW0->ROW7 cycle, UART `ROW_SELECTED,<row>` |
| 2026-08-12 | Codex | Built/flashed ORDER-002A firmware | Build PASS; flash verified successfully |
| 2026-08-12 | Codex | Captured ORDER-002A ROW UART output | `ROW_SELECTED` sequence captured from COM7 |
| 2026-08-12 | User | Reported ORDER-002A ROW voltages | Selected ROWs 0 V; unselected ROWs mostly about 1 V, occasional about 1.3 V |
| 2026-08-12 | Codex | Prepared supervisor reply for ORDER-002A voltage result | `reports/supervisor/2026-08-12_order-002a_row-test-result.md` |
| 2026-08-12 | Supervisor | Issued `ORDER-003` | Standard resistor transfer function, ROW0-COL0 only |
| 2026-08-12 | Codex | Prepared ORDER-003 capture/analysis tooling | Waiting physical resistor sequence |
| 2026-08-12 | Codex | Built/flashed ORDER-003 RAW firmware | Build PASS; flash verified successfully |
| 2026-08-12 | Codex | Captured ORDER-003 RAW mode check | 2 complete frames captured from COM7 |
| 2026-08-13 | User | Reported ORDER-003 issue | `1M` resistor unavailable, replaced by `1.5M`; all captures completed but analysis failed |
| 2026-08-13 | Codex | Diagnosed ORDER-003 run01 | `10k/22k` under 100 samples and target response flat; rework required |
| 2026-08-13 | User | Completed ORDER-003A FAST-A wiring | 10k from U1 Pin2/COL0 TIA negative input to GND |
| 2026-08-13 | Codex | Built/flashed FAST_DEBUG_ROW0 firmware | 100 ms FAST ADC3 8RAW output |
| 2026-08-13 | Codex | Captured FAST-A data | COL0 mean 38215.75 raw, about 1.924 V |
| 2026-08-13 | User | Reported FAST-B wiring fixed | Requested FAST-B retest |
| 2026-08-13 | Codex | Captured FAST-B run02 | COL0 mean 20616.608 raw, about 1.038 V; no ROW0-COL0 response |
| 2026-08-13 | Supervisor | Issued `ORDER-003B` | Stop voltage/debug sweeps; perform power-off continuity check only |
| 2026-08-13 | Codex | Prepared ORDER-003B measurement template and supervisor reply | Waiting for physical continuity results |
| 2026-08-13 | User | Reported suspected open/ROW1 issue fixed | Requested one FAST-B retest |
| 2026-08-13 | Codex | Captured FAST-B run03 | COL0 mean 20607.099 raw, about 1.037666 V; still no ROW0-COL0 response |
| 2026-08-13 | User | Reported wiring/path fixed | Requested FAST-B retest |
| 2026-08-13 | Codex | Captured FAST-B run04 after fix | COL0 mean 38223.725 raw, about 1.924747 V; response observed |
| 2026-08-13 | Supervisor | Issued `ORDER-003E` | Classify Run01 fault and run quick four-point transfer |
| 2026-08-13 | Codex | Prepared ORDER-003E quick analysis and restored scan RAW mode in source | Ready to build, flash, and capture |
| 2026-08-13 | Codex | Built/flashed ORDER-003E normal RAW scan firmware | Build PASS; flash verified successfully |
| 2026-08-13 | Codex | Captured ORDER-003E 10k point | 50 samples; COL0 mean 38220.380 raw, 1.924579 V |
| 2026-08-13 | Codex | Captured ORDER-003E 22k point | 50 samples; COL0 mean 37872.000 raw, 1.907036 V; trend suspect |
| 2026-08-13 | Codex | Captured ORDER-003E 47k point | 50 samples; COL0 mean 20618.500 raw, 1.038240 V; dropped to VREF |
| 2026-08-13 | User | Requested ORDER-003E 47k retest | Repeat 47k instead of moving to 100k |
| 2026-08-13 | Codex | Captured ORDER-003E 47k retest | 50 samples; COL0 mean 20610.700 raw, 1.037847 V; VREF result confirmed |
| 2026-08-13 | User | Requested ORDER-003E 47k second retest | Repeat 47k again |
| 2026-08-13 | Codex | Captured ORDER-003E 47k second retest | 50 samples; COL0 mean 20610.180 raw, 1.037821 V; third VREF result confirmed |
| 2026-08-13 | User | Requested ORDER-003E 100k capture | Continue quick transfer |
| 2026-08-13 | Codex | Captured ORDER-003E 100k point and analyzed four points | 100k near VREF; R2=0.690449; ORDER-003E FAIL |
| 2026-08-13 | Supervisor | Issued `ORDER-DEMO-001` | Restore 8-row scan, baseline/delta threshold demo, heatmap output |
| 2026-08-13 | Codex | Prepared ORDER-DEMO-001 host capture/heatmap script | Ready to build, flash, and run timed press demo |
| 2026-08-13 | Codex | Built/flashed ORDER-DEMO-001 firmware | Build PASS; flash verified successfully; waiting for physical press sequence |
| 2026-08-13 | User | Requested self-run capture controls | Add manual control for local data capture |
| 2026-08-13 | Codex | Fixed ORDER-DEMO-001 script and added manual controls | `-ManualControl` prompts each phase; syntax check PASS |
| 2026-08-13 | User | Reported ORDER-DEMO-001 PNG save failure | GDI+ general error during heatmap save |
| 2026-08-13 | Codex | Hardened ORDER-DEMO-001 heatmap output | Absolute project paths, FileStream PNG save, `-NoHeatmap` fallback; smoke test PASS |
| 2026-08-13 | User | Ran ORDER-DEMO-001 manual capture | `run03_manual` completed |
| 2026-08-13 | Codex | Analyzed ORDER-DEMO-001 run03 manual capture | 100 baseline frames, 100 event frames, 100 heatmaps; press localized at R5/C2, release/second point not separated |
| 2026-08-13 | User | Temporarily removed prior restrictions and requested live pressure program | Single-point pressure heatmap for weights placed anywhere |
| 2026-08-13 | Codex | Implemented live single-point pressure heatmap program | Real-time serial mode plus replay/preview support; relative pressure score only |
| 2026-08-13 | Codex | Verified live pressure heatmap program with existing run03 data | Python compile PASS; preview PNG generated and inspected |
| 2026-08-13 | User | Reported live heatmap field feedback | Multi-point works; static circle jitters; high force/delay; release persistence |
| 2026-08-13 | Codex | Tuned live heatmap V2 | Hide idle marker, lower thresholds, fast attack/release, idle decay, re-zero/clear keys, connected-blob peaks |
| 2026-08-13 | User | Rejected V2 and requested re-optimization from previous version | Position wrong, pressure/release delayed, poor sensitivity; asked current FPS |
| 2026-08-13 | Codex | Implemented live heatmap V3 | App FPS measured 8.7..9.2; raw local peaks, no default smoothing, threshold max(2.5std,60), log throttling, FPS overlay |
| 2026-08-13 | User | Restored strict Gate discipline after report | Codex must submit evidence; user reviews evidence before next ORDER; no evidence no Gate crossing |
| 2026-08-13 | Codex | Archived report acceleration work and restored restrictions | Waiting for next explicit ORDER |
| 2026-08-15 | Supervisor/User | Issued `ORDER-ARCH-01A` | Direct U1A TIA transfer, `U1 Pin2 -> Rtest -> GND`, real sensor COL0 disconnected |
| 2026-08-15 | Codex | Built/flashed `ARCH_01A_DIRECT_TIA` firmware | Build log and flash log saved under `reports/logs/` |
| 2026-08-15 | User/Codex | Captured 14-condition direct TIA sweep | Dataset saved under `data/arch_01a_direct_tia/20260815_033955_run01/` |
| 2026-08-15 | Codex | Analyzed ORDER-ARCH-01A dataset | `FAIL`; R2=0.774574; repeat points inconsistent; supervisor report prepared |
| 2026-08-15 | Supervisor/User | Issued `ORDER-ARCH-01A-R1` | Retest exchange protocol integrity with fixed TEST_A/TEST_B, one condition per process |
| 2026-08-15 | Codex | Prepared R1 capture and analysis tooling | New single-condition capture script and SVG analysis script added; waiting for physical resistor measurements and capture |
| 2026-08-15 | User/Codex | Started R1 100k attempts | 100k partial run marked `INVALID_CONTACT_STATE`; repeated preview loop paused after user frustration |
| 2026-08-15 | Codex | Reported R1 pause to supervisor | Exact physical root cause not identified; recommended lower-friction contact-stability order |
| 2026-08-15 | Supervisor/User | Issued `ORDER-ARCH-01A-R2` | Software acquisition-chain consistency audit, no user resistor changes |
| 2026-08-15 | Codex | Added A01A session id and session-aware readers | Firmware frame now includes session_id; Python readers bind to current session |
| 2026-08-15 | Codex | Ran R2 three-reader comparison | `PASS`; c0 mean spread 0.000322800 V; session consistent; seq gaps 0 |
| 2026-08-15 | Supervisor/User | Issued `ORDER-ARCH-01A-R3A` | Move direct TIA test from U1A/COL0 to U2A/COL2 for cross-channel comparison |
| 2026-08-15 | Codex | Prepared R3A U2/COL2 capture tool | `tools/capture_arch_01a_r3a_u2.py`; waiting for U2 hardware setup and capture |
| 2026-08-15 | User/Supervisor | Issued `ORDER-ADC-01` | Stop R3A path; verify PF6 / ADC3_INP8 with single-channel polling and fixed 100k hardware |
| 2026-08-15 | Codex | Implemented ADC-01 polling firmware and capture script | ADC3 single Rank1 Channel8, DR polling, no DMA, runtime register dump |
| 2026-08-15 | Codex | Built/flashed/captured ORDER-ADC-01 | `PASS`; 1000 samples mean 1.143310 V; seq gaps 0; rail anomalies 0 |
| 2026-08-15 | User/Supervisor | Issued `ORDER-ADC-02` | Add only 8-rank regular scan while keeping polling/no-DMA and fixed 100k hardware |
| 2026-08-15 | Codex | Implemented ADC-02 polling firmware and capture script | ADC3 8 ranks, EOC per conversion, DR polling, no DMA, runtime SQR/PCSEL/DIFSEL dump |
| 2026-08-15 | Codex | Built/flashed/captured ORDER-ADC-02 | `PASS`; rank3/c2 mean 1.143634 V; diff vs ADC-01 +0.000324 V; no invalid frames or seq gaps |
| 2026-08-15 | User/Supervisor | Issued `ORDER-ADC-03A` | Add only original DMA layer for reproduction/audit; no DMA/cache fixes |
| 2026-08-15 | Codex | Implemented ADC-03A DMA baseline audit firmware and capture script | ADC3 8-rank DMA NORMAL, DMA1_Stream1 request ADC3, halfword buffer length 8, runtime DMA/DMAMUX/cache/memory dump |
| 2026-08-15 | Codex | Built/flashed/captured ORDER-ADC-03A | `NOT_REPRODUCED`; rank3/c2 mean 1.143236 V; read_before_tc_count 0; callback_count 1000; no DMA/OVR errors |

## Next Required Evidence

采集链（TIA/ADC3/DMA/软件）已闭环验证，故障归因测试夹具接触不稳定。下一步建议：稳定固定测试点 + 单次干净 10k~1.5M 传递函数复测（见 `方案/8x8_压力矩阵_监工状态文档_v15.md` 第 47 节建议 ORDER-ARCH-01A-R4）。在新 ORDER 下发前：不接真实传感器、不启用 ROW/4051、不进入 ADC-03B/C、不改 Rf/Cf/VREF。
