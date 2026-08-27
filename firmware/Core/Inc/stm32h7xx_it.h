#ifndef STM32H7XX_IT_H
#define STM32H7XX_IT_H

#ifdef __cplusplus
extern "C" {
#endif

void NMI_Handler(void);
void HardFault_Handler(void);
void MemManage_Handler(void);
void BusFault_Handler(void);
void UsageFault_Handler(void);
void SVC_Handler(void);
void DebugMon_Handler(void);
void PendSV_Handler(void);
void SysTick_Handler(void);
void DMA1_Stream1_IRQHandler(void);
void ADC3_IRQHandler(void);

#ifdef __cplusplus
}
#endif

#endif
