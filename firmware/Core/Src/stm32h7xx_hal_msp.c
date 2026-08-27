#include "main.h"

DMA_HandleTypeDef hdma_adc3;

void HAL_MspInit(void)
{
  __HAL_RCC_SYSCFG_CLK_ENABLE();
}

void HAL_ADC_MspInit(ADC_HandleTypeDef *hadc)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};

  if (hadc->Instance != ADC3) {
    return;
  }

  __HAL_RCC_ADC3_CLK_ENABLE();
  __HAL_RCC_ADC_CONFIG(RCC_ADCCLKSOURCE_CLKP);
  __HAL_RCC_GPIOF_CLK_ENABLE();
#if !ADC3_PF6_SINGLE_POLLING_MODE || ADC3_8RANK_SCAN_POLLING_MODE
  __HAL_RCC_GPIOC_CLK_ENABLE();
#endif
#if !ADC3_PF6_SINGLE_POLLING_MODE && !ADC3_8RANK_SCAN_POLLING_MODE
  __HAL_RCC_DMA1_CLK_ENABLE();
#endif

  GPIO_InitStruct.Mode = GPIO_MODE_ANALOG;
  GPIO_InitStruct.Pull = GPIO_NOPULL;

#if ADC3_PF6_SINGLE_POLLING_MODE
  GPIO_InitStruct.Pin = GPIO_PIN_6;
  HAL_GPIO_Init(GPIOF, &GPIO_InitStruct);
#else
  GPIO_InitStruct.Pin = GPIO_PIN_4 | GPIO_PIN_5 | GPIO_PIN_6 | GPIO_PIN_7 | GPIO_PIN_10;
  HAL_GPIO_Init(GPIOF, &GPIO_InitStruct);

  GPIO_InitStruct.Pin = GPIO_PIN_0 | GPIO_PIN_1 | GPIO_PIN_2;
  HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);

#if !ADC3_8RANK_SCAN_POLLING_MODE
  hdma_adc3.Instance = DMA1_Stream1;
  hdma_adc3.Init.Request = DMA_REQUEST_ADC3;
  hdma_adc3.Init.Direction = DMA_PERIPH_TO_MEMORY;
  hdma_adc3.Init.PeriphInc = DMA_PINC_DISABLE;
  hdma_adc3.Init.MemInc = DMA_MINC_ENABLE;
  hdma_adc3.Init.PeriphDataAlignment = DMA_PDATAALIGN_HALFWORD;
  hdma_adc3.Init.MemDataAlignment = DMA_MDATAALIGN_HALFWORD;
  hdma_adc3.Init.Mode = DMA_NORMAL;
  hdma_adc3.Init.Priority = DMA_PRIORITY_HIGH;
  hdma_adc3.Init.FIFOMode = DMA_FIFOMODE_DISABLE;

  if (HAL_DMA_Init(&hdma_adc3) != HAL_OK) {
    Error_Handler();
  }

  __HAL_LINKDMA(hadc, DMA_Handle, hdma_adc3);

  HAL_NVIC_SetPriority(DMA1_Stream1_IRQn, 1, 0);
  HAL_NVIC_EnableIRQ(DMA1_Stream1_IRQn);
  HAL_NVIC_SetPriority(ADC3_IRQn, 1, 1);
  HAL_NVIC_EnableIRQ(ADC3_IRQn);
#endif
#endif
}

void HAL_ADC_MspDeInit(ADC_HandleTypeDef *hadc)
{
  if (hadc->Instance != ADC3) {
    return;
  }

  __HAL_RCC_ADC3_FORCE_RESET();
  __HAL_RCC_ADC3_RELEASE_RESET();
#if ADC3_PF6_SINGLE_POLLING_MODE
  HAL_GPIO_DeInit(GPIOF, GPIO_PIN_6);
#else
  HAL_GPIO_DeInit(GPIOF, GPIO_PIN_4 | GPIO_PIN_5 | GPIO_PIN_6 | GPIO_PIN_7 | GPIO_PIN_10);
  HAL_GPIO_DeInit(GPIOC, GPIO_PIN_0 | GPIO_PIN_1 | GPIO_PIN_2);
#if !ADC3_8RANK_SCAN_POLLING_MODE
  HAL_DMA_DeInit(hadc->DMA_Handle);
  HAL_NVIC_DisableIRQ(DMA1_Stream1_IRQn);
  HAL_NVIC_DisableIRQ(ADC3_IRQn);
#endif
#endif
}

void HAL_UART_MspInit(UART_HandleTypeDef *huart)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};

  if (huart->Instance != USART3) {
    return;
  }

  __HAL_RCC_USART3_CLK_ENABLE();
  __HAL_RCC_GPIOD_CLK_ENABLE();

  GPIO_InitStruct.Pin = GPIO_PIN_8 | GPIO_PIN_9;
  GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  GPIO_InitStruct.Alternate = GPIO_AF7_USART3;
  HAL_GPIO_Init(GPIOD, &GPIO_InitStruct);
}

void HAL_UART_MspDeInit(UART_HandleTypeDef *huart)
{
  if (huart->Instance != USART3) {
    return;
  }

  __HAL_RCC_USART3_CLK_DISABLE();
  HAL_GPIO_DeInit(GPIOD, GPIO_PIN_8 | GPIO_PIN_9);
}
