#ifndef MAIN_H
#define MAIN_H

#ifdef __cplusplus
extern "C" {
#endif

#include "stm32h7xx_hal.h"
#include <stdint.h>

#define ROW_S0_GPIO_Port GPIOE
#define ROW_S0_Pin       GPIO_PIN_14
#define ROW_S1_GPIO_Port GPIOE
#define ROW_S1_Pin       GPIO_PIN_11
#define ROW_S2_GPIO_Port GPIOE
#define ROW_S2_Pin       GPIO_PIN_9
#define ROW_EN_GPIO_Port GPIOG
#define ROW_EN_Pin       GPIO_PIN_5

#define ADC_COL_COUNT             8U
#define MATRIX_ROW_COUNT          8U
#define T_SETTLE_US               500U
#define ROW_ADDR_SETTLE_US        10U
#define ADC_DUMMY_SCANS_PER_ROW   1U
#define ADC_AVG_SCANS_PER_ROW     16U
#define ARCH_01A_DIRECT_TIA_MODE  0U
#define ADC3_PF6_SINGLE_POLLING_MODE 0U
#define ADC3_8RANK_SCAN_POLLING_MODE 0U
#define ADC3_8RANK_DMA_BASELINE_AUDIT_MODE 0U
#define ORDER_002A_ROW_TEST_MODE  0U
#define ORDER_003A_FAST_DEBUG_ROW0_MODE 0U
#define ROW_TEST_PERIOD_MS        2000U
#define FAST_DEBUG_PERIOD_MS      100U
#define ARCH_01A_PERIOD_MS        10U
#define ADC01_PERIOD_MS           10U
#define ADC01_VDDA_UV             3290000UL
#define ADC02_PERIOD_MS           10U
#define ADC02_VDDA_UV             3290000UL
#define ADC03A_PERIOD_MS          10U
#define ADC03A_VDDA_UV            3290000UL
#define FRAME_PERIOD_MS           0U

extern ADC_HandleTypeDef hadc3;
extern DMA_HandleTypeDef hdma_adc3;
extern UART_HandleTypeDef huart3;

void Error_Handler(void);

#ifdef __cplusplus
}
#endif

#endif
