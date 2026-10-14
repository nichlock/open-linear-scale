// Standalone timing benchmark comparing float and double
// arithmetic on this chip. Built via the `bench_softfp` / `bench_hardfp`
// PlatformIO environments in place of the real application, so the same
// file can be compiled once without and once with hardware-FPU flags.

#include <stm32l4xx_hal.h>

#include "main.h"
#include "uart.hpp"

#define FAST_CLOCK 1  // match measure-main-events.cpp: 80MHz SYSCLK

static const uint32_t ITERATIONS = 10000;

void Error_Reporter(void) {
  while (1) {
    __WFI();
  }
}

void SystemClock_Config(void) {
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  if (HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1) != HAL_OK) {
    Error_Handler();
  }

  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_MSI;
  RCC_OscInitStruct.MSIState = RCC_MSI_ON;
  RCC_OscInitStruct.MSICalibrationValue = 0;
  RCC_OscInitStruct.MSIClockRange = RCC_MSIRANGE_6;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_MSI;
  RCC_OscInitStruct.PLL.PLLM = 1;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV7;
  RCC_OscInitStruct.PLL.PLLQ = RCC_PLLQ_DIV2;
#if (FAST_CLOCK == 1)
  RCC_OscInitStruct.PLL.PLLN = 40;
  RCC_OscInitStruct.PLL.PLLR = RCC_PLLR_DIV2;
#else
  RCC_OscInitStruct.PLL.PLLN = 16;
  RCC_OscInitStruct.PLL.PLLR = RCC_PLLR_DIV8;
#endif
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) {
    Error_Handler();
  }

  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV2;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV8;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV16;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_1) != HAL_OK) {
    Error_Handler();
  }
}

static inline void enableCycleCounter() {
  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  DWT->CYCCNT = 0;
  DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

static void reportCycles(const char *type_name, const char *op_name, uint32_t cycles) {
  // Integer math so the report doesn't depend on float printf support
  uint32_t milli_per_op = (uint32_t)((uint64_t)cycles * 1000 / ITERATIONS);
  Uart::cprintf("%s %s: %lu cycles / %lu iters = %lu.%03lu cycles/op\n",
                type_name, op_name, (unsigned long)cycles,
                (unsigned long)ITERATIONS, (unsigned long)(milli_per_op / 1000),
                (unsigned long)(milli_per_op % 1000));
}

static void benchmarkFloat() {
  volatile float a = 1.0f;
  volatile float b = 3.0f;
  volatile float sink;
  uint32_t start, cycles;

  start = DWT->CYCCNT;
  for (uint32_t i = 0; i < ITERATIONS; i++) {
    sink = a + b;
  }
  cycles = DWT->CYCCNT - start;
  reportCycles("float", "add", cycles);

  start = DWT->CYCCNT;
  for (uint32_t i = 0; i < ITERATIONS; i++) {
    sink = a - b;
  }
  cycles = DWT->CYCCNT - start;
  reportCycles("float", "sub", cycles);

  start = DWT->CYCCNT;
  for (uint32_t i = 0; i < ITERATIONS; i++) {
    sink = a * b;
  }
  cycles = DWT->CYCCNT - start;
  reportCycles("float", "mul", cycles);

  start = DWT->CYCCNT;
  for (uint32_t i = 0; i < ITERATIONS; i++) {
    sink = a / b;
  }
  cycles = DWT->CYCCNT - start;
  reportCycles("float", "div", cycles);
  (void)sink;
}

static void benchmarkDouble() {
  volatile double a = 1.0;
  volatile double b = 3.0;
  volatile double sink;
  uint32_t start, cycles;

  start = DWT->CYCCNT;
  for (uint32_t i = 0; i < ITERATIONS; i++) {
    sink = a + b;
  }
  cycles = DWT->CYCCNT - start;
  reportCycles("double", "add", cycles);

  start = DWT->CYCCNT;
  for (uint32_t i = 0; i < ITERATIONS; i++) {
    sink = a - b;
  }
  cycles = DWT->CYCCNT - start;
  reportCycles("double", "sub", cycles);

  start = DWT->CYCCNT;
  for (uint32_t i = 0; i < ITERATIONS; i++) {
    sink = a * b;
  }
  cycles = DWT->CYCCNT - start;
  reportCycles("double", "mul", cycles);

  start = DWT->CYCCNT;
  for (uint32_t i = 0; i < ITERATIONS; i++) {
    sink = a / b;
  }
  cycles = DWT->CYCCNT - start;
  reportCycles("double", "div", cycles);
  (void)sink;
}

int main(void) {
  HAL_Init();
  SystemClock_Config();
  Uart::initUart(DEBUG_UART, DEBUG_BAUDRATE);
  __enable_irq();
  HAL_Delay(100);

  enableCycleCounter();

  Uart::cprintf("\n--- FPU benchmark ---\n");
  Uart::cprintf("SCB->CPACR = 0x%08lx\n", (unsigned long)SCB->CPACR);

  benchmarkFloat();
  benchmarkDouble();

  Uart::cprintf("--- done ---\n");

  while (1) {
    __WFI();
  }
}
