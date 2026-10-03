/* USER CODE BEGIN Header */
/**
 ******************************************************************************
 * @file           : main.h
 * @brief          : Header for main.c file.
 *                   This file contains the common defines of the application.
 ******************************************************************************
 * @attention
 *
 * Copyright (c) 2023 STMicroelectronics.
 * All rights reserved.
 *
 * This software is licensed under terms that can be found in the LICENSE file
 * in the root directory of this software component.
 * If no LICENSE file comes with this software, it is provided AS-IS.
 *
 ******************************************************************************
 */
/* USER CODE END Header */

#ifndef __MAIN_H
#define __MAIN_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief  This function is executed in case of error occurrence.
 * @retval None
 *
 * @param error_code The error code to be displayed on the LEDs. This will
 *                   directly set the timer period.
 *                   for ex: error_code=100 --> 100ms on & off time.
 */
void Error_Reporter(uint32_t error_code);

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
  Error_Reporter(100);
}

// From stm32l4xx_hal_msp.h
extern void HAL_TIM_MspPostInit(TIM_HandleTypeDef* htim);

#ifdef __cplusplus
}
#endif

#endif /* __MAIN_H */
