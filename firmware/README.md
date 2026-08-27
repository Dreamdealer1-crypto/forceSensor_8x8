# ORDER-002 / ORDER-002A / ORDER-003 / ORDER-ARCH-01A Minimal STM32 Firmware

Target: `NUCLEO-H743ZI2` / `STM32H743ZITx`

Scope:

- 4051 row select: `PE14=S0`, `PE11=S1`, `PE9=S2`, `PG5=E/INH`
- ADC3 regular sequence, 8 ranks, fixed `COL0..COL7` order
- DMA one-shot acquisition through `DMA1_Stream1`
- USART3 raw text output at `115200 8N1`
- `T_SETTLE_US = 500`
- Per row: 1 dummy scan discarded, 16 scans averaged
- Linker places RAM at D1 AXI SRAM `0x24000000` so ADC3 DMA can access buffers.

ORDER-002A row-test build mode:

- `ORDER_002A_ROW_TEST_MODE = 0` for ORDER-003.
- ADC/DMA source remains in the project, but the running firmware enters slow ROW test mode before ADC acquisition.
- ROW sequence: `ROW0 -> ROW7`, repeating.
- ROW period: 2000 ms.
- UART line per switch: `ROW_SELECTED,<row>`.

Current ORDER-003 build mode:

- RAW ADC scan enabled.
- Use only a standard resistor between `ROW0` and `COL0`.
- Do not connect the real sensor.
- Do not calculate pressure.

Current ORDER-ARCH-01A build mode:

- `ARCH_01A_DIRECT_TIA_MODE = 1`
- 4051 disabled continuously by holding `PG5` high.
- No ROW scanning is performed.
- ADC3 still samples the same 8 regular ranks in `COL0..COL7` order.
- UART output format:

```text
A01A,<session_id>,<seq>,<timestamp_us>,c0,c1,c2,c3,c4,c5,c6,c7
```

- Intended hardware path is only `U1 Pin2 -> Rtest -> GND`.
- Real sensor `COL0 -> U1 Pin2` must remain disconnected.

Restrictions:

- Do not connect the real fabric sensor.
- Do not output heatmaps.
- Do not calculate pressure values.

Build:

```powershell
cmake -S .\firmware -B .\build\firmware -G Ninja -DCMAKE_BUILD_TYPE=Debug
cmake --build .\build\firmware
```

Flash:

```powershell
.\tools\flash-stm32.ps1 -Firmware .\build\firmware\resist_matrix_minimal.hex
```

Evidence for `ORDER-ARCH-01A` run01 is under:

```text
data/arch_01a_direct_tia/20260815_033955_run01/
reports/notes/2026-08-15_order-arch-01a_direct-tia_result.md
```

`ORDER-ARCH-01A-R1` reuses the same `ARCH_01A_DIRECT_TIA` firmware mode. R1 changes only the physical resistor-change protocol and host capture workflow.

`ORDER-ARCH-01A-R2` adds `session_id` to A01A frames and emits a `BOOT,A01A,<session_id>,...` line so host readers can reject stale or wrong-session data.
