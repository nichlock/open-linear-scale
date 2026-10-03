#ifndef UART_HPP
#define UART_HPP

#include <stm32l4xx_hal.h>

// For variable argument lists and string formatting
#include <stdarg.h>
#include <stdio.h>
#include <stm32l4xx_hal.h>

#ifndef UART_BUFFER_SIZE
  #define UART_BUFFER_SIZE 1024
#endif

/**
 * @brief A class to handle UART communication. All transmission is non-blocking.
 *
 * @tparam _BufferSize The size of the internal tx_buffer to use for transmission.
 */
namespace Uart {

HAL_StatusTypeDef initUart(USART_TypeDef* instance, uint32_t baudrate);
HAL_StatusTypeDef cprintf(const char* fmt, ...);

bool readByte(char* out);  // non-blocking; true if a byte was popped into *out
void pollCommands(void);   // drains pending RX bytes, parses and runs any complete w/r command lines

};  // namespace Uart

// Interrupt handlers

extern "C" {

void DEBUG_UART_IRQHandler(void);

}  // extern "C"

#endif  // End of include guard for UART_HPP