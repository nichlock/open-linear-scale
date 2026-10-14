#ifndef __MAIN_H
#define __MAIN_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif


void Error_Reporter(void);

#include "stm32l4xx_hal.h"

#define DEBUG_UART_NUM 3

#define DEBUG_UART__(n) USART##n
#define DEBUG_UART_(n) DEBUG_UART__(n)
#define DEBUG_UART DEBUG_UART_(DEBUG_UART_NUM)

#define DEBUG_UART_IRQHandler__(n) USART##n##_IRQHandler
#define DEBUG_UART_IRQHandler_(n) DEBUG_UART_IRQHandler__(n)
#define DEBUG_UART_IRQHandler DEBUG_UART_IRQHandler_(DEBUG_UART_NUM)

#define UART_IRQDEBUG_UART_NVIC_IRQ__(n) USART##n##_IRQn
#define DEBUG_UART_NVIC_IRQ_(n) UART_IRQDEBUG_UART_NVIC_IRQ__(n)
#define DEBUG_UART_NVIC_IRQ DEBUG_UART_NVIC_IRQ_(DEBUG_UART_NUM)

/* Exported functions prototypes ---------------------------------------------*/

static inline void Error_Handler(void) {
  Error_Reporter();
}

// From stm32l4xx_hal_msp.h
extern void HAL_TIM_MspPostInit(TIM_HandleTypeDef* htim);

#ifdef __cplusplus
}
#endif

#endif /* __MAIN_H */
