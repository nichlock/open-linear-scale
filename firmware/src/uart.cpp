#include "uart.hpp"

#include <stdlib.h>  // strtoul
#include <string.h>  // memcpy, strtok

#include "main.h"
#include "registers.hpp"

// For floating point formatting
#include <math.h>

UART_HandleTypeDef huart;

char tx_buffer[UART_BUFFER_SIZE] = {0};

// RX ring buffer. Written only by HAL_UART_RxCpltCallback (ISR context),
// read only by Uart::readByte (main loop), so no locking beyond that
// producer/consumer split is needed.
volatile char rx_buffer[UART_BUFFER_SIZE] = {0};
volatile uint16_t rx_head = 0;
volatile uint16_t rx_tail = 0;
static volatile uint8_t rx_byte;

static void armReceive(void) {
  HAL_UART_Receive_IT(&huart, (uint8_t*)&rx_byte, 1);
}

HAL_StatusTypeDef Uart::initUart(USART_TypeDef* instance, uint32_t baudrate) {
  huart.Instance = instance;
  huart.Init.BaudRate = baudrate;

  huart.Init.WordLength = UART_WORDLENGTH_8B;
  huart.Init.StopBits = UART_STOPBITS_1;
  huart.Init.Parity = UART_PARITY_NONE;
  huart.Init.Mode = UART_MODE_TX_RX;
  huart.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart.Init.OverSampling = UART_OVERSAMPLING_8;
  huart.Init.OneBitSampling = UART_ONE_BIT_SAMPLE_DISABLE;
  huart.AdvancedInit.AdvFeatureInit = UART_ADVFEATURE_NO_INIT;

  HAL_StatusTypeDef err = HAL_UART_Init(&huart);

  armReceive();

  return err;
}

HAL_StatusTypeDef vprint(const char* fmt, va_list argp) {
  int len = vsprintf(tx_buffer, fmt, argp);
  if (0 >= len) {
    memcpy(tx_buffer, "<vprint ERROR>", strlen("<vprint ERROR>"));
  }

  HAL_StatusTypeDef status;
  status = HAL_UART_Transmit(&huart, (uint8_t*)tx_buffer, len, 1000);

  return status;
}

HAL_StatusTypeDef Uart::cprintf(const char* fmt, ...) {
  va_list argp;
  va_start(argp, fmt);
  HAL_StatusTypeDef result = vprint(fmt, argp);
  va_end(argp);
  return result;
}

bool Uart::readByte(char* out) {
  if (rx_tail == rx_head) return false;
  *out = rx_buffer[rx_tail];
  rx_tail = (rx_tail + 1) % UART_BUFFER_SIZE;
  return true;
}

namespace {
constexpr size_t CMD_LINE_MAX = 32;

void cmdWrite(char* args) {
  char* idx_str = strtok(args, " ");
  char* val_str = strtok(nullptr, " ");
  if (!idx_str || !val_str) {
    Uart::cprintf("ERR\n");
    return;
  }
  uint32_t idx = strtoul(idx_str, nullptr, 0);
  uint32_t value = strtoul(val_str, nullptr, 0);
  if (!writeRegisterChecked(idx, value)) {
    Uart::cprintf("ERR\n");
    return;
  }
  Uart::cprintf("0x%lx\n", (unsigned long)value);
}

void cmdRead(char* args) {
  char* idx_str = strtok(args, " ");
  char* count_str = strtok(nullptr, " ");
  if (!idx_str) {
    Uart::cprintf("ERR\n");
    return;
  }
  uint32_t idx = strtoul(idx_str, nullptr, 0);
  uint32_t count = count_str ? strtoul(count_str, nullptr, 0) : 1;
  if (count == 0) {
    Uart::cprintf("ERR\n");
    return;
  }
  for (uint32_t i = 0; i < count; i++) {
    uint32_t value;
    if (!readRegisterChecked(idx + i, &value)) {
      Uart::cprintf("ERR\n");
      return;
    }
    Uart::cprintf(i == 0 ? "0x%lx" : " 0x%lx", (unsigned long)value);
  }
  Uart::cprintf("\n");
}

void handleCommandLine(char* line) {
  char* cmd = strtok(line, " ");
  if (!cmd) return;
  char* rest = strtok(nullptr, "");  // remainder of the line, unsplit
  if (cmd[0] == 'w')
    cmdWrite(rest);
  else if (cmd[0] == 'r')
    cmdRead(rest);
  else
    Uart::cprintf("ERR\n");
}
}  // namespace

void Uart::pollCommands(void) {
  static char line_buf[CMD_LINE_MAX];
  static size_t line_len = 0;
  char c;
  while (readByte(&c)) {
    if (c == '\n' || c == '\r') {
      if (line_len > 0) {
        line_buf[line_len] = '\0';
        handleCommandLine(line_buf);
        line_len = 0;
      }
    } else if (line_len < CMD_LINE_MAX - 1) {
      line_buf[line_len++] = c;
    }
    // else: silently drop characters past CMD_LINE_MAX — line is already malformed
  }
}

extern "C" {

void DEBUG_UART_IRQHandler(void) {
  HAL_UART_IRQHandler(&huart);
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef* huart_arg) {
  if (huart_arg->Instance != huart.Instance) return;

  uint16_t next = (rx_head + 1) % UART_BUFFER_SIZE;
  if (next != rx_tail) {  // drop the byte if the ring buffer is full
    rx_buffer[rx_head] = (char)rx_byte;
    rx_head = next;
  }

  armReceive();
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef* huart_arg) {
  if (huart_arg->Instance != huart.Instance) return;

  armReceive();
}

}  // extern "C"
