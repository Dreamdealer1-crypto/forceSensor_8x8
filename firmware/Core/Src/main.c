#include "main.h"
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>

ADC_HandleTypeDef hadc3;
UART_HandleTypeDef huart3;

static volatile bool adc_dma_done;
static uint16_t adc_dma_buffer[ADC_COL_COUNT];
static uint32_t frame_seq;
#if ARCH_01A_DIRECT_TIA_MODE
static uint32_t arch_01a_session_id;
#endif
static bool uart_ready;
static const char *error_context = "unknown";
#if ADC3_8RANK_DMA_BASELINE_AUDIT_MODE
static volatile uint32_t adc03a_callback_count;
#endif

#define ADC3_NO_DMA_POLLING_MODE (ADC3_PF6_SINGLE_POLLING_MODE || ADC3_8RANK_SCAN_POLLING_MODE)

static void MPU_Config(void);
static void SystemClock_Config(void);
static void MX_GPIO_Init(void);
#if !ADC3_NO_DMA_POLLING_MODE
static void MX_DMA_Init(void);
#endif
static void MX_ADC3_Init(void);
static void MX_USART3_UART_Init(void);
static void Row_Select(uint8_t row);
static void Delay_Us(uint32_t us);
static void Uart_Print(const char *text);
static void Uart_Printf(const char *fmt, ...);
#if ADC3_PF6_SINGLE_POLLING_MODE
static void Uart_Print_Voltage_Uv(uint32_t uv);
#endif
static void Scan_One_Row(uint8_t row, uint32_t averages[ADC_COL_COUNT]);
static void Emit_Frame(const uint32_t matrix[MATRIX_ROW_COUNT][ADC_COL_COUNT]);
#if ADC3_PF6_SINGLE_POLLING_MODE
static void Run_Adc01_Pf6_Single_Polling_Mode(void);
static void Emit_Adc01_Register_Dump(void);
static uint16_t Read_Adc3_Pf6_Polling(void);
static uint32_t Raw_To_Uv(uint16_t raw);
#endif
#if ADC3_8RANK_SCAN_POLLING_MODE
static void Run_Adc02_8Rank_Scan_Polling_Mode(void);
static void Emit_Adc02_Register_Dump(void);
static bool Read_Adc3_8Rank_Polling(uint16_t scan[ADC_COL_COUNT]);
#endif
#if ADC3_8RANK_DMA_BASELINE_AUDIT_MODE
static void Run_Adc03a_8Rank_Dma_Baseline_Audit_Mode(void);
static void Emit_Adc03a_Register_Dump(void);
static uint32_t Decode_Sqr_Rank(uint32_t rank_index);
static uint32_t Dma1_Stream1_Error_Flags(void);
#endif
#if ARCH_01A_DIRECT_TIA_MODE
static void Run_Arch_01A_Direct_Tia_Mode(void);
static void Emit_Arch_01A_Frame(uint32_t seq, const uint16_t raw[ADC_COL_COUNT]);
static uint32_t Make_Arch_01A_Session_Id(void);
#endif
#if ORDER_002A_ROW_TEST_MODE
static void Run_Row_Test_Mode(void);
#endif
#if ORDER_003A_FAST_DEBUG_ROW0_MODE
static void Run_Fast_Debug_Row0_Mode(void);
#endif
#if ORDER_003A_FAST_DEBUG_ROW0_MODE || ARCH_01A_DIRECT_TIA_MODE
static void Read_Adc3_Once(uint16_t raw[ADC_COL_COUNT]);
#endif

int main(void)
{
  uint32_t matrix[MATRIX_ROW_COUNT][ADC_COL_COUNT];

  MPU_Config();

  HAL_Init();
  SystemClock_Config();
  MX_GPIO_Init();
#if !ADC3_NO_DMA_POLLING_MODE
  MX_DMA_Init();
#endif
  MX_USART3_UART_Init();
  uart_ready = true;

#if ORDER_002A_ROW_TEST_MODE
  Uart_Print("BOOT,ORDER-002A,row-test-mode\r\n");
  Uart_Print("CFG,ROW_TEST,PERIOD_MS,2000,SEQUENCE,ROW0_TO_ROW7\r\n");
  Uart_Print("CFG,4051,PE14=S0,PE11=S1,PE9=S2,PG5=EN_ACTIVE_LOW\r\n");
  Run_Row_Test_Mode();
#endif

  Uart_Print("BOOT,UART3,ready\r\n");

  MX_ADC3_Init();
  Uart_Print("BOOT,ADC3,ready\r\n");

  if (HAL_ADCEx_Calibration_Start(&hadc3, ADC_CALIB_OFFSET, ADC_SINGLE_ENDED) != HAL_OK) {
    error_context = "adc3-calibration";
    Error_Handler();
  }
  Uart_Print("BOOT,ADC3,calibrated\r\n");

#if ADC3_PF6_SINGLE_POLLING_MODE
  Uart_Print("BOOT,ORDER-ADC-01,ADC3_PF6_SINGLE_POLLING\r\n");
  Uart_Print("CFG,ADC01,PF6,ADC3_INP8,RANK1,SINGLE_CHANNEL,POLLING,NO_DMA,PERIOD_MS,10\r\n");
  Uart_Print("CFG,ADC3_RESOLUTION,16bit\r\n");
  Uart_Print("CFG,ADC3_SAMPLING_TIME,64.5cycles\r\n");
  HAL_Delay(1500U);
  Emit_Adc01_Register_Dump();
  Run_Adc01_Pf6_Single_Polling_Mode();
#endif

#if ADC3_8RANK_SCAN_POLLING_MODE
  Uart_Print("BOOT,ORDER-ADC-02,ADC3_8RANK_SCAN_POLLING\r\n");
  Uart_Print("CFG,ADC02,RANKS,8,POLLING,NO_DMA,PERIOD_MS,10,OUTPUT,ADC02_RAW8\r\n");
  Uart_Print("CFG,ADC3_RESOLUTION,16bit\r\n");
  Uart_Print("CFG,ADC3_SAMPLING_TIME,64.5cycles\r\n");
  HAL_Delay(1500U);
  Emit_Adc02_Register_Dump();
  Run_Adc02_8Rank_Scan_Polling_Mode();
#endif

#if ADC3_8RANK_DMA_BASELINE_AUDIT_MODE
  Uart_Print("BOOT,ORDER-ADC-03A,ADC3_8RANK_DMA_BASELINE_AUDIT\r\n");
  Uart_Print("CFG,ADC03A,RANKS,8,DMA_NORMAL,DMA1_STREAM1,DMA_REQUEST_ADC3,HALFWORD,PERIOD_MS,10,OUTPUT,ADC03A_RAW8_AUDIT\r\n");
  Uart_Print("CFG,ADC3_RESOLUTION,16bit\r\n");
  Uart_Print("CFG,ADC3_SAMPLING_TIME,64.5cycles\r\n");
  HAL_Delay(1500U);
  Emit_Adc03a_Register_Dump();
  Run_Adc03a_8Rank_Dma_Baseline_Audit_Mode();
#endif

  Uart_Print("BOOT,ORDER-003,standard-resistor-transfer,raw-adc-only\r\n");
  Uart_Print("CFG,ADC3_RESOLUTION,16bit\r\n");
  Uart_Print("CFG,ADC3_SAMPLING_TIME,64.5cycles\r\n");
  Uart_Print("CFG,DMA,DMA1_Stream1,DMA_REQUEST_ADC3,NORMAL,HALFWORD\r\n");
  Uart_Print("CFG,ROW,T_SETTLE_US,500,DUMMY,1,AVG,16\r\n");
  Uart_Print("CFG,RANKS,COL0=ADC3_INP9,COL1=ADC3_INP4,COL2=ADC3_INP8,COL3=ADC3_INP3,COL4=ADC3_INP6,COL5=ADC3_INP10,COL6=ADC3_INP11,COL7=ADC3_INP12\r\n");

#if ARCH_01A_DIRECT_TIA_MODE
  arch_01a_session_id = Make_Arch_01A_Session_Id();
  Uart_Printf("BOOT,A01A,%lu,%lu,ARCH_01A_DIRECT_TIA\r\n",
              (unsigned long)arch_01a_session_id,
              (unsigned long)(HAL_GetTick() * 1000UL));
  Uart_Print("CFG,ARCH_01A,4051_DISABLED,PG5_HIGH,NO_ROW_SCAN,PERIOD_MS,10,OUTPUT,A01A_SESSION_RAW8\r\n");
  Run_Arch_01A_Direct_Tia_Mode();
#endif

#if ORDER_003A_FAST_DEBUG_ROW0_MODE
  Uart_Print("BOOT,ORDER-003A,FAST_DEBUG_ROW0\r\n");
  Uart_Print("CFG,FAST_DEBUG,ROW0_SELECTED,PERIOD_MS,100,OUTPUT,ADC3_8RAW\r\n");
  Run_Fast_Debug_Row0_Mode();
#endif

  while (1) {
    for (uint8_t row = 0; row < MATRIX_ROW_COUNT; row++) {
      Scan_One_Row(row, matrix[row]);
    }

    Emit_Frame(matrix);
    if (FRAME_PERIOD_MS > 0U) {
      HAL_Delay(FRAME_PERIOD_MS);
    }
  }
}

#if ADC3_PF6_SINGLE_POLLING_MODE
static void Run_Adc01_Pf6_Single_Polling_Mode(void)
{
  uint32_t seq = 0;
  uint32_t next_tick = HAL_GetTick();

  HAL_GPIO_WritePin(ROW_EN_GPIO_Port, ROW_EN_Pin, GPIO_PIN_SET);

  while (1) {
    if ((seq % 1000UL) == 0UL) {
      Emit_Adc01_Register_Dump();
    }

    uint16_t raw = Read_Adc3_Pf6_Polling();
    uint32_t uv = Raw_To_Uv(raw);

    Uart_Printf("ADC01,%lu,%u,", (unsigned long)seq++, raw);
    Uart_Print_Voltage_Uv(uv);
    Uart_Print("\r\n");

    next_tick += ADC01_PERIOD_MS;
    int32_t wait_ms = (int32_t)(next_tick - HAL_GetTick());
    if (wait_ms > 0) {
      HAL_Delay((uint32_t)wait_ms);
    }
    else {
      next_tick = HAL_GetTick();
    }
  }
}

static void Emit_Adc01_Register_Dump(void)
{
  uint32_t sqr1 = ADC3->SQR1;
  uint32_t sqr2 = ADC3->SQR2;
  uint32_t pcsel = ADC3->PCSEL;
  uint32_t difsel = ADC3->DIFSEL;
  uint32_t cfgr = ADC3->CFGR;
  uint32_t cfgr2 = ADC3->CFGR2;
  uint32_t rank1 = (sqr1 & ADC_SQR1_SQ1_Msk) >> ADC_SQR1_SQ1_Pos;
  uint32_t pcsel_ch8 = (pcsel & (1UL << 8)) ? 1UL : 0UL;
  uint32_t difsel_ch8 = (difsel & (1UL << 8)) ? 1UL : 0UL;
  uint32_t dma = (cfgr & ADC_CFGR_DMNGT_Msk) ? 1UL : 0UL;

  Uart_Printf("ADC01_REG,SQR1,0x%08lX\r\n", (unsigned long)sqr1);
  Uart_Printf("ADC01_REG,SQR2,0x%08lX\r\n", (unsigned long)sqr2);
  Uart_Printf("ADC01_REG,PCSEL,0x%08lX\r\n", (unsigned long)pcsel);
  Uart_Printf("ADC01_REG,DIFSEL,0x%08lX\r\n", (unsigned long)difsel);
  Uart_Printf("ADC01_REG,CFGR,0x%08lX\r\n", (unsigned long)cfgr);
  Uart_Printf("ADC01_REG,CFGR2,0x%08lX\r\n", (unsigned long)cfgr2);
  Uart_Printf("ADC01_DECODE,RANK1,%lu,PCSEL_CH8,%lu,DIFSEL_CH8,%lu,DMA,%lu\r\n",
              (unsigned long)rank1,
              (unsigned long)pcsel_ch8,
              (unsigned long)difsel_ch8,
              (unsigned long)dma);
}

static uint16_t Read_Adc3_Pf6_Polling(void)
{
  uint16_t raw;

  if (HAL_ADC_Start(&hadc3) != HAL_OK) {
    error_context = "adc01-start";
    Error_Handler();
  }

  if (HAL_ADC_PollForConversion(&hadc3, 10) != HAL_OK) {
    error_context = "adc01-poll";
    Error_Handler();
  }

  raw = (uint16_t)HAL_ADC_GetValue(&hadc3);

  if (HAL_ADC_Stop(&hadc3) != HAL_OK) {
    error_context = "adc01-stop";
    Error_Handler();
  }

  return raw;
}

static uint32_t Raw_To_Uv(uint16_t raw)
{
  return (uint32_t)(((uint64_t)raw * ADC01_VDDA_UV + 32767ULL) / 65535ULL);
}
#endif

#if ADC3_8RANK_SCAN_POLLING_MODE
static void Run_Adc02_8Rank_Scan_Polling_Mode(void)
{
  uint16_t scan[ADC_COL_COUNT];
  uint32_t seq = 0;
  uint32_t invalid_frames = 0;
  uint32_t next_tick = HAL_GetTick();

  HAL_GPIO_WritePin(ROW_EN_GPIO_Port, ROW_EN_Pin, GPIO_PIN_SET);

  while (1) {
    if ((seq % 1000UL) == 0UL) {
      Emit_Adc02_Register_Dump();
    }

    if (Read_Adc3_8Rank_Polling(scan)) {
      Uart_Printf("ADC02,%lu", (unsigned long)seq++);
      for (uint32_t rank = 0; rank < ADC_COL_COUNT; rank++) {
        Uart_Printf(",%u", scan[rank]);
      }
      Uart_Print("\r\n");
    }
    else {
      invalid_frames++;
      Uart_Printf("ADC02_INVALID,%lu,%lu\r\n",
                  (unsigned long)seq++,
                  (unsigned long)invalid_frames);
    }

    next_tick += ADC02_PERIOD_MS;
    int32_t wait_ms = (int32_t)(next_tick - HAL_GetTick());
    if (wait_ms > 0) {
      HAL_Delay((uint32_t)wait_ms);
    }
    else {
      next_tick = HAL_GetTick();
    }
  }
}

static uint32_t Decode_Sqr_Rank(uint32_t rank_index)
{
  if (rank_index < 4U) {
    return (ADC3->SQR1 >> (6U + (rank_index * 6U))) & 0x1FUL;
  }
  return (ADC3->SQR2 >> ((rank_index - 4U) * 6U)) & 0x1FUL;
}

static void Emit_Adc02_Register_Dump(void)
{
  const uint32_t expected_channels[ADC_COL_COUNT] = {9U, 4U, 8U, 3U, 6U, 10U, 11U, 12U};
  uint32_t sqr1 = ADC3->SQR1;
  uint32_t sqr2 = ADC3->SQR2;
  uint32_t sqr3 = ADC3->SQR3;
  uint32_t sqr4 = ADC3->SQR4;
  uint32_t pcsel = ADC3->PCSEL;
  uint32_t difsel = ADC3->DIFSEL;
  uint32_t cfgr = ADC3->CFGR;
  uint32_t cfgr2 = ADC3->CFGR2;
  uint32_t ier = ADC3->IER;
  uint32_t isr = ADC3->ISR;
  uint32_t dma = (cfgr & ADC_CFGR_DMNGT_Msk) ? 1UL : 0UL;

  Uart_Printf("ADC02_REG,SQR1,0x%08lX\r\n", (unsigned long)sqr1);
  Uart_Printf("ADC02_REG,SQR2,0x%08lX\r\n", (unsigned long)sqr2);
  Uart_Printf("ADC02_REG,SQR3,0x%08lX\r\n", (unsigned long)sqr3);
  Uart_Printf("ADC02_REG,SQR4,0x%08lX\r\n", (unsigned long)sqr4);
  Uart_Printf("ADC02_REG,PCSEL,0x%08lX\r\n", (unsigned long)pcsel);
  Uart_Printf("ADC02_REG,DIFSEL,0x%08lX\r\n", (unsigned long)difsel);
  Uart_Printf("ADC02_REG,CFGR,0x%08lX\r\n", (unsigned long)cfgr);
  Uart_Printf("ADC02_REG,CFGR2,0x%08lX\r\n", (unsigned long)cfgr2);
  Uart_Printf("ADC02_REG,IER,0x%08lX\r\n", (unsigned long)ier);
  Uart_Printf("ADC02_REG,ISR,0x%08lX\r\n", (unsigned long)isr);
  Uart_Print("ADC02_DECODE");
  for (uint32_t rank = 0; rank < ADC_COL_COUNT; rank++) {
    uint32_t channel = Decode_Sqr_Rank(rank);
    uint32_t expected = expected_channels[rank];
    uint32_t pcsel_bit = (pcsel & (1UL << expected)) ? 1UL : 0UL;
    uint32_t difsel_bit = (difsel & (1UL << expected)) ? 1UL : 0UL;
    Uart_Printf(",R%lu,%lu,PCSEL,%lu,DIFSEL,%lu",
                (unsigned long)(rank + 1U),
                (unsigned long)channel,
                (unsigned long)pcsel_bit,
                (unsigned long)difsel_bit);
  }
  Uart_Printf(",DMA,%lu\r\n", (unsigned long)dma);
}

static bool Read_Adc3_8Rank_Polling(uint16_t scan[ADC_COL_COUNT])
{
  if (HAL_ADC_Start(&hadc3) != HAL_OK) {
    error_context = "adc02-start";
    Error_Handler();
  }

  for (uint32_t rank = 0; rank < ADC_COL_COUNT; rank++) {
    if (HAL_ADC_PollForConversion(&hadc3, 10) != HAL_OK) {
      (void)HAL_ADC_Stop(&hadc3);
      return false;
    }
    scan[rank] = (uint16_t)HAL_ADC_GetValue(&hadc3);
  }

  if (HAL_ADC_Stop(&hadc3) != HAL_OK) {
    error_context = "adc02-stop";
    Error_Handler();
  }

  return true;
}
#endif

#if ADC3_8RANK_DMA_BASELINE_AUDIT_MODE
static uint32_t Decode_Sqr_Rank(uint32_t rank_index)
{
  if (rank_index < 4U) {
    return (ADC3->SQR1 >> (6U + (rank_index * 6U))) & 0x1FUL;
  }
  return (ADC3->SQR2 >> ((rank_index - 4U) * 6U)) & 0x1FUL;
}

static uint32_t Dma1_Stream1_Error_Flags(void)
{
  return DMA1->LISR & (DMA_LISR_FEIF1 | DMA_LISR_DMEIF1 | DMA_LISR_TEIF1);
}

static void Emit_Adc03a_Register_Dump(void)
{
  const uint32_t expected_channels[ADC_COL_COUNT] = {9U, 4U, 8U, 3U, 6U, 10U, 11U, 12U};
  uint32_t sqr1 = ADC3->SQR1;
  uint32_t sqr2 = ADC3->SQR2;
  uint32_t sqr3 = ADC3->SQR3;
  uint32_t sqr4 = ADC3->SQR4;
  uint32_t pcsel = ADC3->PCSEL;
  uint32_t difsel = ADC3->DIFSEL;
  uint32_t cfgr = ADC3->CFGR;
  uint32_t cfgr2 = ADC3->CFGR2;
  uint32_t isr = ADC3->ISR;
  uint32_t dma = (cfgr & ADC_CFGR_DMNGT_Msk) ? 1UL : 0UL;
  uint32_t scb_ccr = SCB->CCR;
  uint32_t dcache_enabled = (scb_ccr & SCB_CCR_DC_Msk) ? 1UL : 0UL;

  Uart_Printf("ADC03A_REG,ADC_SQR1,0x%08lX\r\n", (unsigned long)sqr1);
  Uart_Printf("ADC03A_REG,ADC_SQR2,0x%08lX\r\n", (unsigned long)sqr2);
  Uart_Printf("ADC03A_REG,ADC_SQR3,0x%08lX\r\n", (unsigned long)sqr3);
  Uart_Printf("ADC03A_REG,ADC_SQR4,0x%08lX\r\n", (unsigned long)sqr4);
  Uart_Printf("ADC03A_REG,ADC_PCSEL,0x%08lX\r\n", (unsigned long)pcsel);
  Uart_Printf("ADC03A_REG,ADC_DIFSEL,0x%08lX\r\n", (unsigned long)difsel);
  Uart_Printf("ADC03A_REG,ADC_CFGR,0x%08lX\r\n", (unsigned long)cfgr);
  Uart_Printf("ADC03A_REG,ADC_CFGR2,0x%08lX\r\n", (unsigned long)cfgr2);
  Uart_Printf("ADC03A_REG,ADC_ISR,0x%08lX\r\n", (unsigned long)isr);
  Uart_Printf("ADC03A_REG,DMA1_LISR,0x%08lX\r\n", (unsigned long)DMA1->LISR);
  Uart_Printf("ADC03A_REG,DMA1_HISR,0x%08lX\r\n", (unsigned long)DMA1->HISR);
  Uart_Printf("ADC03A_REG,DMA1_STREAM1_CR,0x%08lX\r\n", (unsigned long)DMA1_Stream1->CR);
  Uart_Printf("ADC03A_REG,DMA1_STREAM1_NDTR,0x%08lX\r\n", (unsigned long)DMA1_Stream1->NDTR);
  Uart_Printf("ADC03A_REG,DMA1_STREAM1_PAR,0x%08lX\r\n", (unsigned long)DMA1_Stream1->PAR);
  Uart_Printf("ADC03A_REG,DMA1_STREAM1_M0AR,0x%08lX\r\n", (unsigned long)DMA1_Stream1->M0AR);
  Uart_Printf("ADC03A_REG,DMA1_STREAM1_FCR,0x%08lX\r\n", (unsigned long)DMA1_Stream1->FCR);
  Uart_Printf("ADC03A_REG,DMAMUX1_CHANNEL1_CCR,0x%08lX\r\n", (unsigned long)DMAMUX1_Channel1->CCR);
  Uart_Printf("ADC03A_REG,SCB_CCR,0x%08lX\r\n", (unsigned long)scb_ccr);
  Uart_Printf("ADC03A_MEM,BUFFER_ADDR,0x%08lX,SIZE,%lu,MOD32,%lu\r\n",
              (unsigned long)(uint32_t)(uintptr_t)adc_dma_buffer,
              (unsigned long)sizeof(adc_dma_buffer),
              (unsigned long)(((uint32_t)(uintptr_t)adc_dma_buffer) % 32UL));
  Uart_Print("ADC03A_DECODE");
  for (uint32_t rank = 0; rank < ADC_COL_COUNT; rank++) {
    uint32_t channel = Decode_Sqr_Rank(rank);
    uint32_t expected = expected_channels[rank];
    uint32_t pcsel_bit = (pcsel & (1UL << expected)) ? 1UL : 0UL;
    uint32_t difsel_bit = (difsel & (1UL << expected)) ? 1UL : 0UL;
    Uart_Printf(",R%lu,%lu,PCSEL,%lu,DIFSEL,%lu",
                (unsigned long)(rank + 1U),
                (unsigned long)channel,
                (unsigned long)pcsel_bit,
                (unsigned long)difsel_bit);
  }
  Uart_Printf(",DMNGT,%lu,DCACHE,%lu,DMAMUX_REQ,%lu\r\n",
              (unsigned long)dma,
              (unsigned long)dcache_enabled,
              (unsigned long)(DMAMUX1_Channel1->CCR & 0x7FUL));
}

static void Run_Adc03a_8Rank_Dma_Baseline_Audit_Mode(void)
{
  uint32_t seq = 0;
  uint32_t next_tick = HAL_GetTick();

  HAL_GPIO_WritePin(ROW_EN_GPIO_Port, ROW_EN_Pin, GPIO_PIN_SET);

  while (1) {
    if ((seq % 1000UL) == 0UL) {
      Emit_Adc03a_Register_Dump();
    }

    memset(adc_dma_buffer, 0, sizeof(adc_dma_buffer));
    adc_dma_done = false;
    uint32_t callback_before = adc03a_callback_count;
    uint32_t ndtr_before_start = DMA1_Stream1->NDTR;

    if (HAL_ADC_Start_DMA(&hadc3, (uint32_t *)adc_dma_buffer, ADC_COL_COUNT) != HAL_OK) {
      error_context = "adc03a-start-dma";
      Error_Handler();
    }
    uint32_t ndtr_after_start = DMA1_Stream1->NDTR;
    uint32_t par_after_start = DMA1_Stream1->PAR;
    uint32_t m0ar_after_start = DMA1_Stream1->M0AR;

    while (!adc_dma_done) {
    }

    uint32_t ndtr_at_read = DMA1_Stream1->NDTR;
    uint32_t callback_seen = (adc03a_callback_count != callback_before) ? 1UL : 0UL;
    uint32_t tc_seen = adc_dma_done ? 1UL : 0UL;
    uint32_t read_before_tc = tc_seen ? 0UL : 1UL;
    uint32_t adc_ovr = (ADC3->ISR & ADC_ISR_OVR) ? 1UL : 0UL;
    uint32_t dma_error_flags = Dma1_Stream1_Error_Flags();

    Uart_Printf("ADC03A,%lu,%lu",
                (unsigned long)seq++,
                (unsigned long)(HAL_GetTick() * 1000UL));
    for (uint32_t index = 0; index < ADC_COL_COUNT; index++) {
      Uart_Printf(",%u", adc_dma_buffer[index]);
    }
    Uart_Printf(",%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,0x%08lX,0x%08lX\r\n",
                (unsigned long)ndtr_before_start,
                (unsigned long)ndtr_after_start,
                (unsigned long)ndtr_at_read,
                (unsigned long)tc_seen,
                (unsigned long)read_before_tc,
                (unsigned long)callback_seen,
                (unsigned long)adc_ovr,
                (unsigned long)dma_error_flags,
                (unsigned long)par_after_start,
                (unsigned long)m0ar_after_start);

    if (HAL_ADC_Stop_DMA(&hadc3) != HAL_OK) {
      error_context = "adc03a-stop-dma";
      Error_Handler();
    }

    next_tick += ADC03A_PERIOD_MS;
    int32_t wait_ms = (int32_t)(next_tick - HAL_GetTick());
    if (wait_ms > 0) {
      HAL_Delay((uint32_t)wait_ms);
    }
    else {
      next_tick = HAL_GetTick();
    }
  }
}
#endif

#if ORDER_003A_FAST_DEBUG_ROW0_MODE
static void Run_Fast_Debug_Row0_Mode(void)
{
  uint16_t raw[ADC_COL_COUNT];
  uint32_t seq = 0;

  Row_Select(0);

  while (1) {
    Read_Adc3_Once(raw);
    Uart_Printf("FAST,%lu,%lu", (unsigned long)seq++, (unsigned long)(HAL_GetTick() * 1000UL));
    for (uint32_t col = 0; col < ADC_COL_COUNT; col++) {
      Uart_Printf(",%u", raw[col]);
    }
    Uart_Print("\r\n");
    HAL_Delay(FAST_DEBUG_PERIOD_MS);
  }
}
#endif

#if ARCH_01A_DIRECT_TIA_MODE
static void Run_Arch_01A_Direct_Tia_Mode(void)
{
  uint16_t raw[ADC_COL_COUNT];
  uint32_t seq = 0;
  uint32_t next_tick = HAL_GetTick();

  HAL_GPIO_WritePin(ROW_EN_GPIO_Port, ROW_EN_Pin, GPIO_PIN_SET);

  while (1) {
    HAL_GPIO_WritePin(ROW_EN_GPIO_Port, ROW_EN_Pin, GPIO_PIN_SET);
    Read_Adc3_Once(raw);
    Emit_Arch_01A_Frame(seq++, raw);

    next_tick += ARCH_01A_PERIOD_MS;
    int32_t wait_ms = (int32_t)(next_tick - HAL_GetTick());
    if (wait_ms > 0) {
      HAL_Delay((uint32_t)wait_ms);
    }
    else {
      next_tick = HAL_GetTick();
    }
  }
}

static void Emit_Arch_01A_Frame(uint32_t seq, const uint16_t raw[ADC_COL_COUNT])
{
  Uart_Printf("A01A,%lu,%lu,%lu",
              (unsigned long)arch_01a_session_id,
              (unsigned long)seq,
              (unsigned long)(HAL_GetTick() * 1000UL));
  for (uint32_t col = 0; col < ADC_COL_COUNT; col++) {
    Uart_Printf(",%u", raw[col]);
  }
  Uart_Print("\r\n");
}

static uint32_t Make_Arch_01A_Session_Id(void)
{
  uint32_t uid0 = HAL_GetUIDw0();
  uint32_t uid1 = HAL_GetUIDw1();
  uint32_t uid2 = HAL_GetUIDw2();
  uint32_t tick = HAL_GetTick();
  uint32_t cycle = DWT->CYCCNT;

  return uid0 ^ (uid1 << 7) ^ (uid2 >> 3) ^ (tick << 16) ^ cycle;
}
#endif

#if ORDER_003A_FAST_DEBUG_ROW0_MODE || ARCH_01A_DIRECT_TIA_MODE
static void Read_Adc3_Once(uint16_t raw[ADC_COL_COUNT])
{
  memset(adc_dma_buffer, 0, sizeof(adc_dma_buffer));
  adc_dma_done = false;

  if (HAL_ADC_Start_DMA(&hadc3, (uint32_t *)adc_dma_buffer, ADC_COL_COUNT) != HAL_OK) {
    error_context = "fast-adc3-start-dma";
    Error_Handler();
  }

  while (!adc_dma_done) {
  }

  if (HAL_ADC_Stop_DMA(&hadc3) != HAL_OK) {
    error_context = "fast-adc3-stop-dma";
    Error_Handler();
  }

  for (uint32_t col = 0; col < ADC_COL_COUNT; col++) {
    raw[col] = adc_dma_buffer[col];
  }
}
#endif

#if ORDER_002A_ROW_TEST_MODE
static void Run_Row_Test_Mode(void)
{
  uint8_t row = 0;

  while (1) {
    Row_Select(row);
    Uart_Printf("ROW_SELECTED,%u\r\n", row);
    HAL_Delay(ROW_TEST_PERIOD_MS);
    row = (uint8_t)((row + 1U) % MATRIX_ROW_COUNT);
  }
}
#endif

static void Scan_One_Row(uint8_t row, uint32_t averages[ADC_COL_COUNT])
{
  uint32_t sums[ADC_COL_COUNT] = {0};

  Row_Select(row);
  Delay_Us(T_SETTLE_US);

  for (uint32_t scan = 0; scan < ADC_DUMMY_SCANS_PER_ROW + ADC_AVG_SCANS_PER_ROW; scan++) {
    memset(adc_dma_buffer, 0, sizeof(adc_dma_buffer));
    adc_dma_done = false;

  if (HAL_ADC_Start_DMA(&hadc3, (uint32_t *)adc_dma_buffer, ADC_COL_COUNT) != HAL_OK) {
      error_context = "adc3-start-dma";
      Error_Handler();
    }

    while (!adc_dma_done) {
    }

    if (HAL_ADC_Stop_DMA(&hadc3) != HAL_OK) {
      error_context = "adc3-stop-dma";
      Error_Handler();
    }

    if (scan < ADC_DUMMY_SCANS_PER_ROW) {
      continue;
    }

    for (uint32_t col = 0; col < ADC_COL_COUNT; col++) {
      sums[col] += adc_dma_buffer[col];
    }
  }

  for (uint32_t col = 0; col < ADC_COL_COUNT; col++) {
    averages[col] = sums[col] / ADC_AVG_SCANS_PER_ROW;
  }
}

static void Emit_Frame(const uint32_t matrix[MATRIX_ROW_COUNT][ADC_COL_COUNT])
{
  Uart_Printf("FRAME,%lu,%lu,1030\r\n", (unsigned long)frame_seq++, (unsigned long)(HAL_GetTick() * 1000UL));

  for (uint32_t row = 0; row < MATRIX_ROW_COUNT; row++) {
    Uart_Printf("R%lu", (unsigned long)row);
    for (uint32_t col = 0; col < ADC_COL_COUNT; col++) {
      Uart_Printf(",%lu", (unsigned long)matrix[row][col]);
    }
    Uart_Print("\r\n");
  }

  Uart_Print("END\r\n");
}

static void Row_Select(uint8_t row)
{
  HAL_GPIO_WritePin(ROW_EN_GPIO_Port, ROW_EN_Pin, GPIO_PIN_SET);
  HAL_GPIO_WritePin(ROW_S0_GPIO_Port, ROW_S0_Pin, (row & 0x01U) ? GPIO_PIN_SET : GPIO_PIN_RESET);
  HAL_GPIO_WritePin(ROW_S1_GPIO_Port, ROW_S1_Pin, (row & 0x02U) ? GPIO_PIN_SET : GPIO_PIN_RESET);
  HAL_GPIO_WritePin(ROW_S2_GPIO_Port, ROW_S2_Pin, (row & 0x04U) ? GPIO_PIN_SET : GPIO_PIN_RESET);
  Delay_Us(ROW_ADDR_SETTLE_US);
  HAL_GPIO_WritePin(ROW_EN_GPIO_Port, ROW_EN_Pin, GPIO_PIN_RESET);
}

static void Delay_Us(uint32_t us)
{
  uint32_t start = DWT->CYCCNT;
  uint32_t cycles = (HAL_RCC_GetHCLKFreq() / 1000000UL) * us;

  while ((DWT->CYCCNT - start) < cycles) {
  }
}

static void Uart_Print(const char *text)
{
  (void)HAL_UART_Transmit(&huart3, (uint8_t *)text, (uint16_t)strlen(text), HAL_MAX_DELAY);
}

static void Uart_Printf(const char *fmt, ...)
{
  char buffer[192];
  va_list args;
  int len;

  va_start(args, fmt);
  len = vsnprintf(buffer, sizeof(buffer), fmt, args);
  va_end(args);

  if (len <= 0) {
    return;
  }

  if ((size_t)len >= sizeof(buffer)) {
    len = (int)sizeof(buffer) - 1;
  }

  (void)HAL_UART_Transmit(&huart3, (uint8_t *)buffer, (uint16_t)len, HAL_MAX_DELAY);
}

#if ADC3_PF6_SINGLE_POLLING_MODE
static void Uart_Print_Voltage_Uv(uint32_t uv)
{
  Uart_Printf("%lu.%06lu",
              (unsigned long)(uv / 1000000UL),
              (unsigned long)(uv % 1000000UL));
}
#endif

void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *hadc)
{
  if (hadc->Instance == ADC3) {
    adc_dma_done = true;
#if ADC3_8RANK_DMA_BASELINE_AUDIT_MODE
    adc03a_callback_count++;
#endif
  }
}

static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};

  __HAL_RCC_GPIOE_CLK_ENABLE();
  __HAL_RCC_GPIOG_CLK_ENABLE();

  HAL_GPIO_WritePin(ROW_EN_GPIO_Port, ROW_EN_Pin, GPIO_PIN_SET);
  HAL_GPIO_WritePin(GPIOE, ROW_S0_Pin | ROW_S1_Pin | ROW_S2_Pin, GPIO_PIN_RESET);

  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;

  GPIO_InitStruct.Pin = ROW_S0_Pin | ROW_S1_Pin | ROW_S2_Pin;
  HAL_GPIO_Init(GPIOE, &GPIO_InitStruct);

  GPIO_InitStruct.Pin = ROW_EN_Pin;
  HAL_GPIO_Init(GPIOG, &GPIO_InitStruct);
}

#if !ADC3_NO_DMA_POLLING_MODE
static void MX_DMA_Init(void)
{
  __HAL_RCC_DMA1_CLK_ENABLE();
}
#endif

static void MX_ADC3_Init(void)
{
  ADC_ChannelConfTypeDef sConfig = {0};
#if !ADC3_NO_DMA_POLLING_MODE || ADC3_8RANK_SCAN_POLLING_MODE
  const uint32_t channels[ADC_COL_COUNT] = {
      ADC_CHANNEL_9,
      ADC_CHANNEL_4,
      ADC_CHANNEL_8,
      ADC_CHANNEL_3,
      ADC_CHANNEL_6,
      ADC_CHANNEL_10,
      ADC_CHANNEL_11,
      ADC_CHANNEL_12,
  };
  const uint32_t ranks[ADC_COL_COUNT] = {
      ADC_REGULAR_RANK_1,
      ADC_REGULAR_RANK_2,
      ADC_REGULAR_RANK_3,
      ADC_REGULAR_RANK_4,
      ADC_REGULAR_RANK_5,
      ADC_REGULAR_RANK_6,
      ADC_REGULAR_RANK_7,
      ADC_REGULAR_RANK_8,
  };
#endif

  hadc3.Instance = ADC3;
  hadc3.Init.ClockPrescaler = ADC_CLOCK_ASYNC_DIV8;
  hadc3.Init.Resolution = ADC_RESOLUTION_16B;
#if ADC3_PF6_SINGLE_POLLING_MODE
  hadc3.Init.ScanConvMode = ADC_SCAN_DISABLE;
  hadc3.Init.EOCSelection = ADC_EOC_SINGLE_CONV;
  hadc3.Init.NbrOfConversion = 1;
  hadc3.Init.ConversionDataManagement = ADC_CONVERSIONDATA_DR;
#elif ADC3_8RANK_SCAN_POLLING_MODE
  hadc3.Init.ScanConvMode = ADC_SCAN_ENABLE;
  hadc3.Init.EOCSelection = ADC_EOC_SINGLE_CONV;
  hadc3.Init.NbrOfConversion = ADC_COL_COUNT;
  hadc3.Init.ConversionDataManagement = ADC_CONVERSIONDATA_DR;
#else
  hadc3.Init.ScanConvMode = ADC_SCAN_ENABLE;
  hadc3.Init.EOCSelection = ADC_EOC_SEQ_CONV;
  hadc3.Init.NbrOfConversion = ADC_COL_COUNT;
  hadc3.Init.ConversionDataManagement = ADC_CONVERSIONDATA_DMA_ONESHOT;
#endif
  hadc3.Init.LowPowerAutoWait = DISABLE;
  hadc3.Init.ContinuousConvMode = DISABLE;
  hadc3.Init.DiscontinuousConvMode = DISABLE;
  hadc3.Init.NbrOfDiscConversion = 1;
  hadc3.Init.ExternalTrigConv = ADC_SOFTWARE_START;
  hadc3.Init.ExternalTrigConvEdge = ADC_EXTERNALTRIGCONVEDGE_NONE;
  hadc3.Init.Overrun = ADC_OVR_DATA_PRESERVED;
  hadc3.Init.LeftBitShift = ADC_LEFTBITSHIFT_NONE;
  hadc3.Init.OversamplingMode = DISABLE;

  if (HAL_ADC_Init(&hadc3) != HAL_OK) {
    error_context = "adc3-init";
    Error_Handler();
  }

  sConfig.SamplingTime = ADC_SAMPLETIME_64CYCLES_5;
  sConfig.SingleDiff = ADC_SINGLE_ENDED;
  sConfig.OffsetNumber = ADC_OFFSET_NONE;
  sConfig.Offset = 0;

#if ADC3_PF6_SINGLE_POLLING_MODE
  sConfig.Channel = ADC_CHANNEL_8;
  sConfig.Rank = ADC_REGULAR_RANK_1;
  if (HAL_ADC_ConfigChannel(&hadc3, &sConfig) != HAL_OK) {
    error_context = "adc3-config-pf6-channel8";
    Error_Handler();
  }
#else
  for (uint32_t index = 0; index < ADC_COL_COUNT; index++) {
    sConfig.Channel = channels[index];
    sConfig.Rank = ranks[index];
    if (HAL_ADC_ConfigChannel(&hadc3, &sConfig) != HAL_OK) {
      error_context = "adc3-config-channel";
      Error_Handler();
    }
  }
#endif
}

static void MX_USART3_UART_Init(void)
{
  huart3.Instance = USART3;
  huart3.Init.BaudRate = 115200;
  huart3.Init.WordLength = UART_WORDLENGTH_8B;
  huart3.Init.StopBits = UART_STOPBITS_1;
  huart3.Init.Parity = UART_PARITY_NONE;
  huart3.Init.Mode = UART_MODE_TX_RX;
  huart3.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart3.Init.OverSampling = UART_OVERSAMPLING_16;
  huart3.Init.OneBitSampling = UART_ONE_BIT_SAMPLE_DISABLE;
  huart3.Init.ClockPrescaler = UART_PRESCALER_DIV1;
  huart3.AdvancedInit.AdvFeatureInit = UART_ADVFEATURE_NO_INIT;

  if (HAL_UART_Init(&huart3) != HAL_OK) {
    Error_Handler();
  }

  if (HAL_UARTEx_SetTxFifoThreshold(&huart3, UART_TXFIFO_THRESHOLD_1_8) != HAL_OK) {
    error_context = "uart3-tx-fifo";
    Error_Handler();
  }

  if (HAL_UARTEx_SetRxFifoThreshold(&huart3, UART_RXFIFO_THRESHOLD_1_8) != HAL_OK) {
    error_context = "uart3-rx-fifo";
    Error_Handler();
  }

  if (HAL_UARTEx_DisableFifoMode(&huart3) != HAL_OK) {
    error_context = "uart3-disable-fifo";
    Error_Handler();
  }
}

static void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};
  RCC_PeriphCLKInitTypeDef PeriphClkInitStruct = {0};

  HAL_PWREx_ConfigSupply(PWR_LDO_SUPPLY);
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);
  while (!__HAL_PWR_GET_FLAG(PWR_FLAG_VOSRDY)) {
  }

  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_BYPASS;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLM = 4;
  RCC_OscInitStruct.PLL.PLLN = 400;
  RCC_OscInitStruct.PLL.PLLP = 2;
  RCC_OscInitStruct.PLL.PLLQ = 4;
  RCC_OscInitStruct.PLL.PLLR = 2;
  RCC_OscInitStruct.PLL.PLLRGE = RCC_PLL1VCIRANGE_1;
  RCC_OscInitStruct.PLL.PLLVCOSEL = RCC_PLL1VCOWIDE;
  RCC_OscInitStruct.PLL.PLLFRACN = 0;

  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) {
    error_context = "rcc-osc";
    Error_Handler();
  }

  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK |
                                RCC_CLOCKTYPE_D1PCLK1 | RCC_CLOCKTYPE_PCLK1 |
                                RCC_CLOCKTYPE_PCLK2 | RCC_CLOCKTYPE_D3PCLK1;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.SYSCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB3CLKDivider = RCC_APB3_DIV2;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_APB1_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_APB2_DIV2;
  RCC_ClkInitStruct.APB4CLKDivider = RCC_APB4_DIV2;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_4) != HAL_OK) {
    error_context = "rcc-clock";
    Error_Handler();
  }

  PeriphClkInitStruct.PeriphClockSelection = RCC_PERIPHCLK_ADC | RCC_PERIPHCLK_USART3;
  PeriphClkInitStruct.PLL2.PLL2M = 4;
  PeriphClkInitStruct.PLL2.PLL2N = 100;
  PeriphClkInitStruct.PLL2.PLL2P = 10;
  PeriphClkInitStruct.PLL2.PLL2Q = 10;
  PeriphClkInitStruct.PLL2.PLL2R = 10;
  PeriphClkInitStruct.PLL2.PLL2RGE = RCC_PLL2VCIRANGE_1;
  PeriphClkInitStruct.PLL2.PLL2VCOSEL = RCC_PLL2VCOWIDE;
  PeriphClkInitStruct.PLL2.PLL2FRACN = 0;
  PeriphClkInitStruct.AdcClockSelection = RCC_ADCCLKSOURCE_PLL2;
  PeriphClkInitStruct.Usart234578ClockSelection = RCC_USART234578CLKSOURCE_D2PCLK1;

  if (HAL_RCCEx_PeriphCLKConfig(&PeriphClkInitStruct) != HAL_OK) {
    error_context = "rcc-periph-clock";
    Error_Handler();
  }
}

static void MPU_Config(void)
{
  MPU_Region_InitTypeDef MPU_InitStruct = {0};

  HAL_MPU_Disable();

  MPU_InitStruct.Enable = MPU_REGION_ENABLE;
  MPU_InitStruct.Number = MPU_REGION_NUMBER0;
  MPU_InitStruct.BaseAddress = 0x00000000;
  MPU_InitStruct.Size = MPU_REGION_SIZE_4GB;
  MPU_InitStruct.SubRegionDisable = 0x87;
  MPU_InitStruct.TypeExtField = MPU_TEX_LEVEL0;
  MPU_InitStruct.AccessPermission = MPU_REGION_NO_ACCESS;
  MPU_InitStruct.DisableExec = MPU_INSTRUCTION_ACCESS_DISABLE;
  MPU_InitStruct.IsShareable = MPU_ACCESS_SHAREABLE;
  MPU_InitStruct.IsCacheable = MPU_ACCESS_NOT_CACHEABLE;
  MPU_InitStruct.IsBufferable = MPU_ACCESS_NOT_BUFFERABLE;

  HAL_MPU_ConfigRegion(&MPU_InitStruct);
  HAL_MPU_Enable(MPU_PRIVILEGED_DEFAULT);

  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  DWT->CYCCNT = 0;
  DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

void Error_Handler(void)
{
  if (uart_ready) {
    Uart_Print("ERROR,");
    Uart_Print(error_context);
    Uart_Print("\r\n");
  }
  __disable_irq();
  while (1) {
  }
}
