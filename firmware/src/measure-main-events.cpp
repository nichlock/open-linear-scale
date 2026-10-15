// #include <stdio.h>
#include <stm32l4xx_hal.h>
#include <string.h>  // memcpy

#include <cinttypes>  // PRIx32
#include <cstring>    // std::memcpy used for float-to-bits conversion in register space

#include "main.h"
#include "registers.hpp"
#include "sensor-math.hpp"
#include "uart.hpp"
#include "util/filters.hpp"

// for ADC LL init
#include <stm32l4xx_ll_adc.h>
#include <stm32l4xx_ll_bus.h>
#include <stm32l4xx_ll_cortex.h>
#include <stm32l4xx_ll_dma.h>
#include <stm32l4xx_ll_gpio.h>
#include <stm32l4xx_ll_pwr.h>
#include <stm32l4xx_ll_rcc.h>
#include <stm32l4xx_ll_system.h>
#include <stm32l4xx_ll_tim.h>
#include <stm32l4xx_ll_utils.h>
// for ADC LL init
#include <stm32l4xx_ll_exti.h>
// for PWR HAL
#include <stm32l4xx_hal_pwr.h>

void SystemClock_Config(void);
void PeriphCommonClock_Config(void);
// static void MX_GPIO_Init(bool disable_debug_pins = false);
static void MX_DMA_Init(void);
static void MX_ADC1_Init(void);
// static void MX_ADC2_Init(void);
static void MX_DAC1_Init(void);
// static void MX_USART2_UART_Init(void);
static void MX_TIM2_Init(void);
static void MX_TIM5_Init(void);
static void MX_OPAMP1_Init(void);
static void MX_OPAMP2_Init(void);

///////////////////////////////////////////////////////////////////////////////
// ADC input config

struct AdcInputPin {
  uint32_t adc_channel;
  GPIO_TypeDef* gpio;
  uint32_t gpio_num;
  AdcInputPin(uint32_t ch, GPIO_TypeDef* io, uint32_t num)
      : adc_channel(ch), gpio(io), gpio_num(num) {}
};

// clang-format off
#define ADC_INPUT_LIST(X) \
  X(INPUT_COUNTER            , AdcInputPin(0, nullptr, 0)) \
  X(INPUT_DAC                , AdcInputPin(LL_ADC_CHANNEL_9 , GPIOA, LL_GPIO_PIN_4)) \
  X(INPUT_INTEGRATOR         , AdcInputPin(LL_ADC_CHANNEL_15, GPIOB, LL_GPIO_PIN_0)) \
  X(INPUT_FILTER             , AdcInputPin(LL_ADC_CHANNEL_8 , GPIOA, LL_GPIO_PIN_3)) \
  // clang-format on

enum AdcInputIndex : uint8_t {
#define X(name, value) name,
  ADC_INPUT_LIST(X)
#undef X
      ADC_INPUT_COUNT
};

AdcInputPin adc_input_options[ADC_INPUT_COUNT] = {
#define X(name, value) (value),
    ADC_INPUT_LIST(X)
#undef X
};

///////////////////////////////////////////////////////////////////////////////
// Register Helpers
uint32_t bit_cast_f2i(float x) {
  uint32_t ret = 0;
  std::memcpy(&ret, &x, sizeof(ret));
  return ret;
}

float bit_cast_i2f(uint32_t x) {
  float ret = 0;
  std::memcpy(&ret, &x, sizeof(ret));
  return ret;
}

///////////////////////////////////////////////////////////////////////////////
// Register space

enum SampleOutputTypes : uint8_t {
  OUTPUT_FLOATING_TEXT = 0,  // Plaintext position (1.23\n)
  OUTPUT_FLOATING_HEX,       // Position as the binary float data in hex formatting (1234abcd)
  OUTPUT_DBG_BURST_RAW,      // Take no differences
  OUTPUT_DBG_BURST_DIFF,     // Take the diff and cancel out opposite emitters
  OUTPUT_DBG_NONE,           // Run sensor without outputting for electrical measurements
};

enum StateMachine : uint8_t {
  STATE_START_CONTINUOUS = 0,
  STATE_STOP,
  _STATE_BARRIER,  // Values at and below this cannot be selected by an external user (needs to happen automatically)
  STATE_CONTINUOUS,
  STATE_STOPPED,
  STATE_ERROR = 99,
};

enum SensorAlgorithms : uint8_t {
  ALGO_SLIDING_WINDOW = 0,
  ALGO_DBG_IND_EMITTERS,  // Individual emitters are driven high then low.
};

// Register Permissions
// Read
const uint8_t P_RD = 0x1;
// Write while paused
const uint8_t P_WP = 0x2;
// Write while running samples
const uint8_t P_WR = 0x4;

// clang-format off
#define REGISTER_LIST(X) \
/* These registers are expected to be used most often */ \
  X(READING_F                    , 0                                     , P_RD)    \
  X(ERROR_VALUE                  , 0                                     , P_RD | P_WP | P_WR) \
  X(SENSOR_STATE                 , STATE_START_CONTINUOUS                , P_RD | P_WP | P_WR) \
  /* default unit is mm */ \
  X(CONVERSION_FACTOR            , bit_cast_f2i(0.635f)                  , P_RD | P_WP | P_WR) \
  /* float, added to the tare offset then reset to 0 on the next measurement */ \
  X(SENSOR_TARE                  , 0                                     , P_RD | P_WP | P_WR) \
  /* Sample configuration, can only happen while a sample is not running */ \
  X(SENSOR_INPUT                 , INPUT_FILTER                          , P_RD | P_WP) \
  X(SENSOR_OUTPUT                , OUTPUT_FLOATING_HEX                   , P_RD | P_WP) \
  X(SENSOR_ALGORITHM             , ALGO_SLIDING_WINDOW                   , P_RD | P_WP) \
  X(SEQUENCE_TIME_US             , 1000                                  , P_RD | P_WP) \
  X(TX_RX_DELAY_US               , 38                                    , P_RD | P_WP) \
  X(CONVERSION_WINDOW            , LL_ADC_SAMPLINGTIME_12CYCLES_5        , P_RD | P_WP) \
  X(DISCARD_FIRST_SEQUENCE       , 1                                     , P_RD | P_WP) \
  X(BURST_COUNT                  , 2048                                  , P_RD | P_WP) \
  X(BURST_OFFSET_ENABLE          , 0                                     , P_RD | P_WP) \
  /* These are informational only */ \
  X(TRUE_OVERSAMPLE_CYCLE_NS     , 0                                     , P_RD) \
  X(TRUE_ADC_CONVERSION_NS       , 0                                     , P_RD) \
  X(TRUE_ADC_DELAY_NS            , 0                                     , P_RD) \
  X(SEQUENCE_TIMER_FREQ          , 0                                     , P_RD) \
  X(TRUE_CONV_PER_OVERSAMPLE     , 0                                     , P_RD) \
  X(TRUE_ADC_OVERSAMPLE_TIME_NS  , 0                                     , P_RD) \
  // clang-format on

enum RegIndex : uint8_t {
#define X(name, init, perms) name,
  REGISTER_LIST(X)
#undef X
      REG_COUNT
};

uint32_t registers[REG_COUNT] = {
#define X(name, init, perms) (init),
    REGISTER_LIST(X)
#undef X
};

uint32_t permissions[REG_COUNT] = {
#define X(name, init, perms) (perms),
    REGISTER_LIST(X)
#undef X
};

///////////////////////////////////////////////////////////////////////////////
// Misclaneous

// clang-format off
typedef enum {
  ERRFLAG_BAD_CONFIG              = 1ul << 0,   // Bad register configuration provided
  ERRFLAG_BAD_SENSOR_INPUT        = 1ul << 1,
  ERRFLAG_BAD_SEQUENCE_TIMING     = 1ul << 2,
  ERRFLAG_UNKOWN_ALGO             = 1ul << 4,
  ERRFLAG_EMITTER_DMA             = 1ul << 5,   // Transfer error on the emitter DMA channel
  ERRFLAG_ADC_DMA                 = 1ul << 6,   // Transfer error on the ADC DMA channel
  ERRFLAG_BURST_CONFIG            = 1ul << 7,   // BURST_COUNT is larger than the burst buffer
  // ERRFLAG_RESERVED                = 1ul << 8,
  // ERRFLAG_RESERVED                = 1ul << 9,
  // ERRFLAG_RESERVED                = 1ul << 10,
  // ERRFLAG_RESERVED                = 1ul << 11,
  // ERRFLAG_RESERVED                = 1ul << 12,
  // ERRFLAG_RESERVED                = 1ul << 13,
  // ERRFLAG_RESERVED                = 1ul << 14,
  // ERRFLAG_RESERVED                = 1ul << 15,
  // ERRFLAG_RESERVED                = 1ul << 16,
  // ERRFLAG_RESERVED                = 1ul << 17,
  // ERRFLAG_RESERVED                = 1ul << 18,
  // ERRFLAG_RESERVED                = 1ul << 19,
  // ERRFLAG_RESERVED                = 1ul << 21,
  // ERRFLAG_RESERVED                = 1ul << 22,
  // ERRFLAG_RESERVED                = 1ul << 23,
  // ERRFLAG_RESERVED                = 1ul << 24,
  // ERRFLAG_RESERVED                = 1ul << 25,
  // ERRFLAG_RESERVED                = 1ul << 26,
  // ERRFLAG_RESERVED                = 1ul << 27,
  ERRFLAG_DROPPED_SEQUENCES       = 1ul << 28,  // One or more sequences were not converted.
  ERRFLAG_TIMER_INTERRUPT         = 1ul << 29,  // An error happened in the TIM interrupt
  ERRFLAG_ADC_INTERRUPT           = 1ul << 30,  // An error happened in the ADC interrupt
  ERRFLAG_DMA_STACK_SMASH         = 1ul << 31,  // DMA ran over the intended array.
} ErrorFlag;
// clang-format on

void error(ErrorFlag error_type);

// Sampling ADC
ADC_TypeDef* adc_s = ADC1;
// Sampling timer
TIM_TypeDef* tim_s = TIM2;

///////////////////////////////////////////////////////////////////////////////
// Emitter pinouts

/// The emitter pinout; emitter zero on pin emitter_pins[0], one on emitter_pins[1], etc...
const static uint32_t emitter_pins[algo::EMITTER_COUNT] = {13, 14, 15, 9, 8, 7, 6, 2};
/// The emitter port. All emitters are on one port by design.
#define emitter_GPIOx GPIOC

uint32_t emitter_state_gpio_bsrr[algo::EMITTER_STATE_COUNT] = {0};

///////////////////////////////////////////////////////////////////////////////
// Sample config
//
// Sample Naming Convention
// There are several types of samples that run at many different rates.
// 1. **Conversion**: ADC individual sample/convert cycle
// 2. **Oversample**: The value once the ADC's hardware oversample completes.
// 3. **Sequence**:   The overall sequence running at 1kHz.
//
// There is also a **Transient**: This is a logical-only value. It represents the
// oversampled values after some cancellations/transforms are performed.

algo::adcreading_t readings_unsafe[algo::EMITTER_STATE_COUNT + 1] = {0};
algo::adcreading_t readings_shared[algo::EMITTER_STATE_COUNT] = {0};

#define BURST_BUFFER_ALLOC (2048)
algo::adcreading_t burst_buf[BURST_BUFFER_ALLOC][algo::EMITTER_STATE_COUNT / 2] = {0};
size_t burst_iterator = 0;

typedef uint32_t smplidx_t;
smplidx_t readings_sequence = 0;
smplidx_t tx_step = 0;

const static algo::adcreading_t STACK_SMASH_MAGIC_VAL = 0xAAAAAAAAul;

extern "C" {
void ADC1_2_IRQHandler(void) {
  uint8_t isr_known = 0;

  if (adc_s->ISR & ADC_FLAG_EOC) {
    // Clear interrupt flag
    LL_ADC_ClearFlag_EOC(adc_s);

    if (registers[SENSOR_INPUT] == INPUT_COUNTER) {
      // Take a reading and ignore it to prevent overrun errors
      volatile uint32_t reading = LL_ADC_REG_ReadConversionData12(adc_s);
      (void)reading;
      isr_known = 1;
    }
  }

  if (adc_s->ISR & ADC_FLAG_EOS) {
    LL_ADC_ClearFlag_EOS(adc_s);
    LL_ADC_REG_StartConversion(adc_s);
    isr_known = 1;
  }

  if (!isr_known) {
    // Error condition: interrupt not recognized
    error(ERRFLAG_ADC_INTERRUPT);
  }
}  // ADC1_2_IRQHandler

void DMA1_Channel1_IRQHandler(void) {
  if (DMA1->ISR & DMA_ISR_TEIF1) {
    DMA1->IFCR = DMA_IFCR_CGIF1;
    error(ERRFLAG_ADC_DMA);
    return;
  }

  DMA1_Channel1->CCR &= ~DMA_CCR_EN;
  DMA1_Channel1->CNDTR = algo::EMITTER_STATE_COUNT;
  DMA1_Channel1->CCR |= DMA_CCR_EN;
  LL_DMA_ClearFlag_GI1(DMA1);

  memcpy(readings_shared, readings_unsafe, sizeof(readings_shared));
  readings_sequence++;
}

void DMA1_Channel2_IRQHandler(void) {
  if (DMA1->ISR & DMA_ISR_TEIF2) {
    DMA1->IFCR = DMA_IFCR_CGIF2;
    error(ERRFLAG_EMITTER_DMA);
  }
}

}  // extern "C"

void startBackgroundSampling(void) {
  tx_step = 0;

  tim_s->CNT = 0;

  DMA1_Channel1->CNDTR = algo::EMITTER_STATE_COUNT;

  // Restart the emitter table from state 0, even after a mid-sequence stop
  DMA1_Channel2->CNDTR = algo::EMITTER_STATE_COUNT;

  __disable_irq();
  HAL_NVIC_EnableIRQ(ADC1_2_IRQn);
  HAL_NVIC_EnableIRQ(DMA1_Channel1_IRQn);
  HAL_NVIC_EnableIRQ(DMA1_Channel2_IRQn);
  __enable_irq();

  adc_s->CR |= ADC_CR_ADEN;

  while ((adc_s->CR & ADC_CR_ADEN) != ADC_CR_ADEN) {
    __WFE();
  }

  // Arm the ADC
  // Despite its name, this won't start a conversion, but will tell the ADC
  // to wait for a trigger from the timer.
  LL_ADC_REG_StartConversion(adc_s);

  // The emitter DMA must be armed before update requests are enabled so the
  // first update event is not missed.
  tim_s->SR = 0;
  DMA1_Channel2->CCR |= DMA_CCR_EN;

  // Enable timer interrupt and emitter DMA request on counter overflow
  tim_s->DIER |= TIM_DIER_UDE;

  DMA1_Channel1->CCR |= DMA_CCR_EN;

  // Enable timer counting
  tim_s->CR1 |= TIM_CR1_CEN;
}

void stopBackgroundSampling(void) {
  tim_s->CR1 &= ~TIM_CR1_CEN;
  tim_s->DIER &= ~TIM_DIER_UDE;
  DMA1_Channel2->CCR &= ~DMA_CCR_EN;
  LL_ADC_REG_StopConversion(adc_s);
  DMA1_Channel1->CCR &= ~DMA_CCR_EN;

  // Prevent a running conversion IRQ from messing with
  // the control registers during reconfiguration
  __disable_irq();
  HAL_NVIC_DisableIRQ(ADC1_2_IRQn);
  HAL_NVIC_DisableIRQ(DMA1_Channel1_IRQn);
  HAL_NVIC_DisableIRQ(DMA1_Channel2_IRQn);
  __enable_irq();

  if (LL_ADC_IsEnabled(adc_s)) {
    // Make sure ADC conversion is compeletely stopped
    while (LL_ADC_REG_IsConversionOngoing(adc_s) || LL_ADC_REG_IsStopConversionOngoing(adc_s)) {
      __WFE();
    }

    // Disable ADC and wait for disable to succeed
    adc_s->CR |= ADC_CR_ADDIS;
    while (LL_ADC_IsEnabled(adc_s) || LL_ADC_IsDisableOngoing(adc_s)) {
      __WFE();
    }
  }
}

bool isSampleStopped() {
  return registers[SENSOR_STATE] == STATE_STOPPED;
}

bool writeRegisterChecked(uint32_t idx, uint32_t value) {
  if (idx >= REG_COUNT) return false;
  uint32_t required_perm = isSampleStopped() ? P_WP : P_WR;

  if (idx == SENSOR_STATE && value >= _STATE_BARRIER) {
    return false;
  }

  if (idx == ERROR_VALUE && value != 0) {
    return false;
  }

  if (!(permissions[idx] & required_perm)) {
    return false;
  }

  registers[idx] = value;
  return true;
}

bool readRegisterChecked(uint32_t idx, uint32_t* out) {
  if (idx >= REG_COUNT) return false;
  if (!(permissions[idx] & P_RD)) return false;
  *out = registers[idx];
  return true;
}

smplidx_t waitForCurrentSequenceEnd() {
  smplidx_t sequence_number = readings_sequence;
  while (sequence_number == readings_sequence) {
    __WFE();
  }
  return readings_sequence;
}

void safePullReadings(algo::adcreading_t destination[16]) {
  smplidx_t seq_before, seq_after;
  do {
    NVIC_DisableIRQ(DMA1_Channel1_IRQn);
    seq_before = readings_sequence;
    memcpy(destination, readings_shared, sizeof(readings_shared));
    seq_after = readings_sequence;
    NVIC_EnableIRQ(DMA1_Channel1_IRQn);
  } while (seq_before != seq_after);
}

void error(ErrorFlag error_type) {
  registers[ERROR_VALUE] |= error_type;
  stopBackgroundSampling();
  registers[SENSOR_STATE] = STATE_ERROR;
}

/**
 * @brief Fills the emitter_state_gpio_bsrr array with GPIO writes that will
 *        output the pre-configured emitter states.
 *
 */
ErrorStatus generateEmitterStateDataWrites(void) {
  if (registers[SENSOR_ALGORITHM] == ALGO_SLIDING_WINDOW) {
    for (size_t state = 0; state < algo::EMITTER_STATE_COUNT; state++) {
      uint32_t set = 0;
      uint32_t res = 0;
      for (size_t bit = 0; bit < algo::EMITTER_COUNT; bit++) {
        if ((1ul << bit) & algo::emitter_states[state])
          set |= 1ul << emitter_pins[bit];
        else
          res |= 1ul << emitter_pins[bit];
      }  // for (bit)

      emitter_state_gpio_bsrr[state] = (res << 16) | (set);
    }  // for (state)
  } else if (registers[SENSOR_ALGORITHM] == ALGO_DBG_IND_EMITTERS) {
    for (size_t state = 0; state < algo::EMITTER_STATE_COUNT; state++) {
      uint32_t gpio = 1 << emitter_pins[(state >> 1)];
      if (state & 1ul) {
        emitter_state_gpio_bsrr[state] = (gpio << 16);
      } else {
        emitter_state_gpio_bsrr[state] = (gpio);
      }
    }  // for (state)
  } else {
    error(ERRFLAG_UNKOWN_ALGO);
    return ErrorStatus::ERROR;
  }
  return ErrorStatus::SUCCESS;
}

/**
 * @brief Configure the GPIOs for the emitters based on the emitter_pins pinmap.
 */
void initializeEmitterPins(void) {
  uint32_t new_moder_msk = 0;
  uint32_t new_moder_set = 0;

  uint32_t new_otyper_msk = 0;
  uint32_t new_otyper_set = 0;

  uint32_t new_ospeed_msk = 0;
  uint32_t new_ospeed_set = 0;

  for (size_t bit = 0; bit < algo::EMITTER_COUNT; bit++) {
    new_moder_msk |= GPIO_MODER_MODE0_Msk << (2 * emitter_pins[bit]);
    new_moder_set |= GPIO_MODE_OUTPUT_PP << (2 * emitter_pins[bit]);

    new_otyper_msk |= GPIO_OTYPER_OT0_Msk << emitter_pins[bit];
    new_otyper_set |= 0x0ul << emitter_pins[bit];  // Not needed here, only need to clear

    new_ospeed_msk |= 0x0ul << emitter_pins[bit];  // Not needed here, only need to set
    new_ospeed_set |= 0x3ul << (2 * emitter_pins[bit]);
  }  // for (bit)

  // Apply the generated values
  emitter_GPIOx->MODER &= ~new_moder_msk;
  emitter_GPIOx->MODER |= new_moder_set;

  emitter_GPIOx->OTYPER &= ~new_otyper_msk;
  emitter_GPIOx->OTYPER |= new_otyper_set;

  // emitter_GPIOx->OSPEEDR &= ~new_ospeed_msk;
  // emitter_GPIOx->OSPEEDR |= new_ospeed_set;
}

float adcConversionLengthSeconds(uint32_t setting) {
  uint32_t adc_freq = HAL_RCCEx_GetPeriphCLKFreq(RCC_PERIPHCLK_ADC);
  uint32_t cycle_count = 0;
  switch (setting) {
    case LL_ADC_SAMPLINGTIME_2CYCLES_5:
      cycle_count = 2 + 13;
      break;
    case LL_ADC_SAMPLINGTIME_6CYCLES_5:
      cycle_count = 6 + 13;
      break;
    case LL_ADC_SAMPLINGTIME_12CYCLES_5:
      cycle_count = 12 + 13;
      break;
    case LL_ADC_SAMPLINGTIME_24CYCLES_5:
      cycle_count = 24 + 13;
      break;
    case LL_ADC_SAMPLINGTIME_47CYCLES_5:
      cycle_count = 47 + 13;
      break;
    case LL_ADC_SAMPLINGTIME_92CYCLES_5:
      cycle_count = 92 + 13;
      break;
    case LL_ADC_SAMPLINGTIME_247CYCLES_5:
      cycle_count = 247 + 13;
      break;
    case LL_ADC_SAMPLINGTIME_640CYCLES_5:
      cycle_count = 640 + 13;
      break;
    default:
      cycle_count = 0;
  }

  return float(cycle_count) / float(adc_freq);
}

ErrorStatus configureAdcInputGpio() {
  // note, all registers used here are assumed to contain valid values.
  for (size_t channel = 0; channel < ADC_INPUT_COUNT; channel++) {
    LL_GPIO_DisablePinAnalogControl(adc_input_options[channel].gpio, adc_input_options[channel].gpio_num);
  }

  const AdcInputPin& adc_pin = adc_input_options[registers[SENSOR_INPUT]];

  if (adc_pin.gpio == nullptr) {
    // The selection is a debugging input from memory, not a real analog input
    return ErrorStatus::SUCCESS;
  }

  LL_GPIO_InitTypeDef GPIO_InitStruct = {0};
  GPIO_InitStruct.Pin = adc_pin.gpio_num;
  GPIO_InitStruct.Mode = LL_GPIO_MODE_ANALOG;
  GPIO_InitStruct.Pull = LL_GPIO_PULL_NO;
  ErrorStatus status = LL_GPIO_Init(adc_pin.gpio, &GPIO_InitStruct);

  LL_GPIO_EnablePinAnalogControl(adc_pin.gpio, adc_pin.gpio_num);

  LL_ADC_REG_SetSequencerRanks(adc_s, LL_ADC_REG_RANK_1, adc_pin.adc_channel);
  LL_ADC_SetChannelSamplingTime(adc_s, adc_pin.adc_channel, registers[CONVERSION_WINDOW]);
  LL_ADC_SetChannelSingleDiff(adc_s, adc_pin.adc_channel, LL_ADC_SINGLE_ENDED);

  return status;
}

void initializeSampleFrontend() {
  adc_s->CR &= ~ADC_CR_ADEN;
  tim_s->CCER |= TIM_CCER_CC2E;
  tim_s->CCMR1 = 0;
  tim_s->CCMR1 |= 0x7ul << TIM_CCMR1_OC2M_Pos;

  // ADC must re-arm itself after each oversample completes
  adc_s->IER |= ADC_IER_EOS;

  // Allow ADC to take CC2 triggers
  adc_s->CFGR &= ~(ADC_CFGR_EXTSEL_Msk);
  adc_s->CFGR |= LL_ADC_REG_TRIG_EXT_TIM2_CH2;

  adc_s->CFGR &= ~ADC_CFGR_EXTEN_Msk;
  adc_s->CFGR |= 0x1ul << ADC_CFGR_EXTEN_Pos;

  // Enable oversampling
  adc_s->CFGR2 |= ADC_CFGR2_ROVSE;

  DMA1_CSELR->CSELR &= ~DMA_CSELR_C1S_Msk;

  DMA1_Channel1->CCR = 0;
  DMA1_Channel1->CCR = DMA_CCR_TCIE | DMA_CCR_TEIE | DMA_CCR_MINC | DMA_CCR_PSIZE_1 | DMA_CCR_MSIZE_1 | DMA_CCR_PL_1;

  // Configure timer for emitter GPIO writes
  DMA1_CSELR->CSELR &= ~DMA_CSELR_C2S_Msk;
  DMA1_CSELR->CSELR |= 0x4ul << DMA_CSELR_C2S_Pos;  // TIM2_UP

  DMA1_Channel2->CCR = 0;
  DMA1_Channel2->CCR = DMA_CCR_DIR | DMA_CCR_CIRC | DMA_CCR_MINC | DMA_CCR_PSIZE_1 | DMA_CCR_MSIZE_1 |
                       DMA_CCR_PL_1 | DMA_CCR_PL_0 | DMA_CCR_TEIE;
  DMA1_Channel2->CPAR = (uint32_t)(&emitter_GPIOx->BSRR);
  DMA1_Channel2->CMAR = (uint32_t)emitter_state_gpio_bsrr;
}

ErrorStatus configureSampleFrontend() {
  stopBackgroundSampling();

  // Before commiting anything to hardware, any dependant registers are validated

  if (registers[SENSOR_INPUT] >= ADC_INPUT_COUNT) {
    error(ERRFLAG_BAD_SENSOR_INPUT);
    return ErrorStatus::ERROR;
  }

  if (registers[BURST_COUNT] > BURST_BUFFER_ALLOC) {
    error(ERRFLAG_BURST_CONFIG);
    return ErrorStatus::ERROR;
  }

  // Configure sequence timer clock
  registers[SEQUENCE_TIMER_FREQ] = HAL_RCC_GetPCLK1Freq() * 2;

  float tim_clk = registers[SEQUENCE_TIMER_FREQ];
  uint32_t target_tim_arr = ((registers[SEQUENCE_TIME_US] * tim_clk) / 1e6) / algo::EMITTER_STATE_COUNT;

  // An arbitrary maximum of 1s is imposed here.
  // 100us is a guess at where things will start to break down. TODO: validate it.
  if (target_tim_arr <= 100 || target_tim_arr > 1e6) {
    error(ERRFLAG_BAD_SEQUENCE_TIMING);
    return ErrorStatus::ERROR;
  }

  // Set the ADC trigger CC channel
  uint32_t target_tim_cc = ((registers[TX_RX_DELAY_US] * tim_clk) / 1e6);

  if (target_tim_cc >= target_tim_arr) {
    // This might work, but it is not intended behaviour, and could lead to race conditions
    error(ERRFLAG_BAD_SEQUENCE_TIMING);
    return ErrorStatus::ERROR;
  }

  float adc_window_s = adcConversionLengthSeconds(registers[CONVERSION_WINDOW]);

  // Use adcConversionLengthSeconds as a proxy to tell us whether this was a valid option
  if (adc_window_s == 0) {
    error(ERRFLAG_BAD_SEQUENCE_TIMING);
    return ErrorStatus::ERROR;
  }

  float conversion_period = float(registers[SEQUENCE_TIME_US]) / (float(algo::EMITTER_STATE_COUNT) * 1e6);

  registers[TRUE_OVERSAMPLE_CYCLE_NS] = int32_t(conversion_period * 1e9);
  registers[TRUE_ADC_CONVERSION_NS] = int32_t(adc_window_s * 1e9);
  registers[TRUE_ADC_DELAY_NS] = int32_t(1e9 * (float(target_tim_cc) / float(tim_clk)));

  // 0.9 is added here as timing margin
  uint32_t num_oversamples = 0.9 * conversion_period / adc_window_s;

  int bits = 0;
  while (num_oversamples != 0) {
    num_oversamples >>= 1;
    bits++;
  }
  bits -= 1;
  num_oversamples = 1ul << (bits);

  registers[TRUE_CONV_PER_OVERSAMPLE] = num_oversamples;

  float total_adc_sample_time = adc_window_s * num_oversamples;
  registers[TRUE_ADC_OVERSAMPLE_TIME_NS] = uint32_t(total_adc_sample_time * 1e9);

  // The ADC supports oversample ratios of 2x (bits = 1) to 256x (bits = 8)
  if (bits <= 0 || bits > 8) {
    error(ERRFLAG_BAD_SEQUENCE_TIMING);
    return ErrorStatus::ERROR;
  }

  // registers ok, continue to write to hardware.

  if (adc_input_options[registers[SENSOR_INPUT]].gpio == nullptr) {
    // The input type is memory-only and the DMA won't read ADC DR.
    // The ADC will raise an overrun error if we don't read the DR manually.
    adc_s->IER |= ADC_IER_EOC;
  } else {
    adc_s->IER &= ~ADC_IER_EOC;
  }

  // A minimum of 1 count is required (TODO: is this true anymore?)
  target_tim_cc = (target_tim_cc) ? (target_tim_cc) : 1;

  tim_s->ARR = target_tim_arr;
  tim_s->CCR2 = target_tim_cc;

  if (registers[SENSOR_INPUT] == INPUT_COUNTER) {
    DMA1_Channel1->CCR |= DMA_CCR_MEM2MEM;
    DMA1_Channel1->CPAR = (uint32_t)(&tx_step);
  } else {
    DMA1_Channel1->CCR &= ~DMA_CCR_MEM2MEM;
    DMA1_Channel1->CPAR = (uint32_t)(&adc_s->DR);
  }

  DMA1_Channel1->CMAR = (uint32_t)readings_unsafe;
  DMA1_Channel1->CNDTR = algo::EMITTER_STATE_COUNT;

  uint32_t ovsr = (bits - 1) & 0x7ul;
  uint32_t ovss = (bits >= 4) ? (bits - 4) : 0;
  // uint32_t ovss = 2; // (bits - 2) & 0xFul;

  // Uart::cprintf("OVSR: 0x%02x\n", ovsr);
  // Uart::cprintf("OVSS: 0x%02x\n", ovss);

  adc_s->CFGR2 &= ~ADC_CFGR2_OVSR_Msk;
  adc_s->CFGR2 |= ovsr << ADC_CFGR2_OVSR_Pos;

  adc_s->CFGR2 &= ~ADC_CFGR2_OVSS_Msk;
  adc_s->CFGR2 |= ovss << ADC_CFGR2_OVSS_Pos;

  configureAdcInputGpio();

  // Enable ADC
  // DMA1_Channel1->CCR |= DMA_CCR_EN;
  adc_s->CR |= ADC_CR_ADEN;

  return ErrorStatus::SUCCESS;
}

void initIrqPriorities(void) {
  int priority = 0;

  HAL_NVIC_SetPriority(DMA1_Channel1_IRQn, priority++, 0);
  HAL_NVIC_EnableIRQ(DMA1_Channel1_IRQn);

  HAL_NVIC_SetPriority(DMA1_Channel2_IRQn, priority++, 0);
  HAL_NVIC_EnableIRQ(DMA1_Channel2_IRQn);

  HAL_NVIC_SetPriority(ADC1_2_IRQn, priority++, 0);
  HAL_NVIC_EnableIRQ(ADC1_2_IRQn);

  HAL_NVIC_SetPriority(DEBUG_UART_NVIC_IRQ, priority++, 0);
  HAL_NVIC_EnableIRQ(DEBUG_UART_NVIC_IRQ);
}

int main(void) {
// Power-down FLASH memory to save power
#if POWER_SAVING
  FLASH->ACR |= FLASH_ACR_RUN_PD;
#endif

  // Reset of all peripherals, Initializes the Flash interface and the Systick.
  HAL_Init();

  readings_unsafe[algo::EMITTER_STATE_COUNT] = STACK_SMASH_MAGIC_VAL;

  // Configure the system clock
  SystemClock_Config();

  // Configure the peripherals common clocks
  PeriphCommonClock_Config();

  // Enable UART printing
  // MX_USART2_UART_Init();
  Uart::initUart(DEBUG_UART, DEBUG_BAUDRATE);

  // Slow UART lines to minimum slew
  // GPIOA->OSPEEDR &= ~0xF0ul; // USART2
  GPIOC->OSPEEDR &= ~(GPIO_OSPEEDER_OSPEEDR10 | GPIO_OSPEEDER_OSPEEDR11);  // USART3

  // setPrintfUart(huart2);
  // setPrintfUart(uart);

  // Enable global IRQs
  __enable_irq();

  Uart::cprintf("Startup\n");

  MX_OPAMP2_Init();  // Charge integrator
  MX_OPAMP1_Init();  // Filter
  MX_DMA_Init();
  MX_ADC1_Init();
  MX_DAC1_Init();  // DAC for opamp bias
  MX_TIM2_Init();  // Timer for ADC sampling
  MX_TIM5_Init();  // Timer for slack time measurement

// Enable low-power run mode
#if POWER_SAVING
  PWR->CR1 |= PWR_CR1_LPR;
#endif

  // Write emitter pin modes
  initializeEmitterPins();

  // Set up NVIC priorities
  initIrqPriorities();

  initializeSampleFrontend();

  // Allow analog circuits to settle
  HAL_Delay(100);

  algo::fixedpos_t incremental_position = 0, prv_inc_pos = 0, absolute_position = 0;
  algo::fixedpos_t tared_position = 0;
  // Accumulated tare, in unscaled position units
  algo::fixedpos_t tare_offset = 0;
  // algo::fixedpos_t absolute_position_filtered = 0;

  algo::adcreading_t readings[algo::EMITTER_STATE_COUNT] = {0};
  algo::adcreading_t mapped_readings[algo::EMITTER_PERIOD][2];

  // Assume that the voltage has settled since boot
  // This could be replaced with an ADC read, but the first cycle data should
  // be discarded anyway.
  algo::adcreading_t final_oversample = 1ul << 15;

  smplidx_t prev_seq_num = 0, new_seq_num = 0;

  uint32_t last_reported_error = 0;

  while (1) {
    Uart::pollCommands();

    if (registers[ERROR_VALUE] != last_reported_error) {
      // Only report if the error is newly high
      if (registers[ERROR_VALUE] & (last_reported_error ^ registers[ERROR_VALUE])) {
        Uart::cprintf("ERROR DETECTED: registers[ERROR_VALUE] = 0x%x\n", registers[ERROR_VALUE]);
      }
      last_reported_error = registers[ERROR_VALUE];
    }

    if (registers[SENSOR_STATE] == STATE_STOP) {
      stopBackgroundSampling();
      registers[SENSOR_STATE] = STATE_STOPPED;
    }

    if (registers[SENSOR_STATE] == STATE_STOPPED || registers[SENSOR_STATE] == STATE_ERROR) {
      continue;
    } else if (registers[SENSOR_STATE] == STATE_START_CONTINUOUS) {
      if (generateEmitterStateDataWrites() != ErrorStatus::SUCCESS) {
        error(ERRFLAG_BAD_CONFIG);
        continue;
      }
      if (configureSampleFrontend() != ErrorStatus::SUCCESS) {
        error(ERRFLAG_BAD_CONFIG);
        continue;
      }
      prev_seq_num = readings_sequence;
      startBackgroundSampling();
      registers[SENSOR_STATE] = STATE_CONTINUOUS;
    }

    // This is mostly historical now that DMA is used, but it can be good
    // for catching misconfigured DMA.
    if (readings_unsafe[algo::EMITTER_STATE_COUNT] != STACK_SMASH_MAGIC_VAL) {
      Uart::cprintf("Stack smashing detected (%x)\n", readings_unsafe[algo::EMITTER_STATE_COUNT]);
      error(ERRFLAG_DMA_STACK_SMASH);
      readings_unsafe[algo::EMITTER_STATE_COUNT] = STACK_SMASH_MAGIC_VAL;
    }

    new_seq_num = waitForCurrentSequenceEnd();

    if (smplidx_t(prev_seq_num + 1) != new_seq_num) {
      Uart::cprintf("Missed sequences (%d, %d)\n", prev_seq_num, new_seq_num);
      error(ERRFLAG_DROPPED_SEQUENCES);
    }
    prev_seq_num = new_seq_num;

    // This pulls readings without allowing for an intermediate DMA interrupt
    // to cause data corruption.
    // If a DMA interrupt does happen, it will be caught by the above code
    // checking for dropped sequence cycles.
    safePullReadings(readings);

    if (registers[SENSOR_OUTPUT] == OUTPUT_DBG_BURST_DIFF ||
        registers[SENSOR_OUTPUT] == OUTPUT_FLOATING_TEXT ||
        registers[SENSOR_OUTPUT] == OUTPUT_FLOATING_HEX) {
    // Remap emitter readings based on the order of inputs.
    // There are two characteristics to consider.
    // 1) readings[i] = -readings[i+8], so they are combined to make a larger signal
    // 2) readings[i] is taken as a measruement to ground. But, the previous reading
    //    had already offset the signal from the midway point. So, taking
    //    readings[i] - reeadings[i-1] will get the full, uncoupled transient magnitude.
    //
    // We can't take readings[-1], so for the first transient we store memory of the last
    // transient that happened.
    // clang-format off
    mapped_readings[0][1] = (readings[0] - final_oversample) - (readings[ 8] - readings[ 7]);
    mapped_readings[1][1] = (readings[2] - readings[1])     - (readings[10] - readings[ 9]);
    mapped_readings[2][1] = (readings[4] - readings[3])     - (readings[12] - readings[11]);
    mapped_readings[3][1] = (readings[6] - readings[5])     - (readings[14] - readings[13]);
    mapped_readings[0][0] = (readings[1] - readings[0])     - (readings[ 9] - readings[ 8]);
    mapped_readings[1][0] = (readings[3] - readings[2])     - (readings[11] - readings[10]);
    mapped_readings[2][0] = (readings[5] - readings[4])     - (readings[13] - readings[12]);
    mapped_readings[3][0] = (readings[7] - readings[6])     - (readings[15] - readings[14]);
    final_oversample = readings[15];
      // clang-format on
    } else if (registers[SENSOR_OUTPUT] == OUTPUT_DBG_BURST_RAW) {
      // Only capture the raw values of the first set of readings, without zeroing.
      // This is intended for noise analysis. It is only useful when paired with
      // one of the output modes that reports raw transient measurements.
      if (!registers[BURST_OFFSET_ENABLE]) {
        mapped_readings[0][0] = readings[0];
        mapped_readings[1][0] = readings[1];
        mapped_readings[2][0] = readings[2];
        mapped_readings[3][0] = readings[3];
        mapped_readings[0][1] = readings[4];
        mapped_readings[1][1] = readings[5];
        mapped_readings[2][1] = readings[6];
        mapped_readings[3][1] = readings[7];
      } else {
        mapped_readings[0][0] = readings[8];
        mapped_readings[1][0] = readings[9];
        mapped_readings[2][0] = readings[10];
        mapped_readings[3][0] = readings[11];
        mapped_readings[0][1] = readings[12];
        mapped_readings[1][1] = readings[13];
        mapped_readings[2][1] = readings[14];
        mapped_readings[3][1] = readings[15];
      }
    }

    incremental_position = algo::evalPosition(mapped_readings);
    algo::updatePosition(incremental_position, prv_inc_pos, absolute_position);
    float conversion_factor = bit_cast_i2f(registers[CONVERSION_FACTOR]);

    // Pull any pending tare. It is consumed here so each write applies once.
    if (registers[SENSOR_TARE] != 0) {
      tare_offset += bit_cast_i2f(registers[SENSOR_TARE]) / conversion_factor;
      registers[SENSOR_TARE] = 0;
    }
    tared_position = (absolute_position - tare_offset) * conversion_factor;

    registers[READING_F] = bit_cast_f2i(tared_position);

    if (registers[SENSOR_OUTPUT] == OUTPUT_FLOATING_TEXT) {
      Uart::cprintf("%f\n", tared_position);

    } else if (registers[SENSOR_OUTPUT] == OUTPUT_FLOATING_HEX) {
      Uart::cprintf("%08" PRIx32 "\n", bit_cast_f2i(tared_position));

    } else if ((registers[SENSOR_OUTPUT] == OUTPUT_DBG_BURST_DIFF) || (registers[SENSOR_OUTPUT] == OUTPUT_DBG_BURST_RAW)) {
      for (size_t i = 0; i < 4; i++) {
        for (size_t j = 0; j < 2; j++)
          burst_buf[burst_iterator][i + (4 * j)] = mapped_readings[i][j];
      }

      burst_iterator++;
      if (burst_iterator >= registers[BURST_COUNT]) {
        burst_iterator = 0;

        stopBackgroundSampling();

        Uart::cprintf("Sequence Rate: %d ticks at %d Hz\n", tim_s->ARR * algo::EMITTER_STATE_COUNT, (uint32_t)registers[SEQUENCE_TIMER_FREQ]);

        // Discard the first sequence. Useful if there is a period of
        // down-time since the last sequence.
        // During that down-time, the ADC sampling capacitor falls to zero.
        // During the very first set of oversamples, it needs to get charged
        // back up near VCC/2. That can take time depending on the input method.
        for (size_t rd = registers[DISCARD_FIRST_SEQUENCE]; rd < registers[BURST_COUNT]; rd++) {
          Uart::cprintf("%ld,%d,%d,%d,%d,%d,%d,%d,%d,%d\n",
                        rd,
                        burst_buf[rd][0],
                        burst_buf[rd][1],
                        burst_buf[rd][2],
                        burst_buf[rd][3],
                        burst_buf[rd][4],
                        burst_buf[rd][5],
                        burst_buf[rd][6],
                        burst_buf[rd][7],

                        burst_buf[rd][0] +
                            burst_buf[rd][1] +
                            burst_buf[rd][2] +
                            burst_buf[rd][3] +
                            burst_buf[rd][4] +
                            burst_buf[rd][5] +
                            burst_buf[rd][6] +
                            burst_buf[rd][7]);
        }

        Uart::cprintf("end\n");

        startBackgroundSampling();
      }
    }

    // // Double-precision floating-point is required for IIR filters
    // // absolute_position_filtered = algo::fixedpos_t(filter.filter(absolute_position.toDouble()));

    // // Moving average filter is fine with fixed-point
    // absolute_position_filtered = filter.filter(absolute_position);

    // // Skip filtering altogether
    // // absolute_position_filtered = absolute_position;

    // HAL_Delay(10);

  }  // while(1)
}  // main()

/**
 * @brief System Clock Configuration
 * @retval None
 */
void SystemClock_Config(void) {
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
   */
  if (HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1) != HAL_OK) {
    Error_Handler();
  }

  /** Initializes the RCC Oscillators according to the specified parameters
   * in the RCC_OscInitTypeDef structure.
   */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_MSI;
  RCC_OscInitStruct.MSIState = RCC_MSI_ON;
  RCC_OscInitStruct.MSICalibrationValue = 0;
  RCC_OscInitStruct.MSIClockRange = RCC_MSIRANGE_6;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_MSI;
  RCC_OscInitStruct.PLL.PLLM = 1;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV7;
  RCC_OscInitStruct.PLL.PLLQ = RCC_PLLQ_DIV2;
  RCC_OscInitStruct.PLL.PLLN = 40;
  RCC_OscInitStruct.PLL.PLLR = RCC_PLLR_DIV2;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
   */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV2;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV8;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV16;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_1) != HAL_OK) {
    Error_Handler();
  }
}

/**
 * @brief Peripherals Common Clock Configuration
 * @retval None
 */
void PeriphCommonClock_Config(void) {
  RCC_PeriphCLKInitTypeDef PeriphClkInit = {0};

  /** Initializes the peripherals clock
   */
  PeriphClkInit.PeriphClockSelection = RCC_PERIPHCLK_ADC;
  PeriphClkInit.AdcClockSelection = RCC_ADCCLKSOURCE_SYSCLK;
  PeriphClkInit.PLLSAI1.PLLSAI1Source = RCC_PLLSOURCE_MSI;
  PeriphClkInit.PLLSAI1.PLLSAI1M = 1;
  PeriphClkInit.PLLSAI1.PLLSAI1N = 16;
  PeriphClkInit.PLLSAI1.PLLSAI1P = RCC_PLLP_DIV7;
  PeriphClkInit.PLLSAI1.PLLSAI1Q = RCC_PLLQ_DIV2;
  PeriphClkInit.PLLSAI1.PLLSAI1R = RCC_PLLR_DIV8;
  PeriphClkInit.PLLSAI1.PLLSAI1ClockOut = RCC_PLLSAI1_ADC1CLK;
  if (HAL_RCCEx_PeriphCLKConfig(&PeriphClkInit) != HAL_OK) {
    Error_Handler();
  }
}

static void MX_DMA_Init(void) {
  /* DMA controller clock enable */
  __HAL_RCC_DMA1_CLK_ENABLE();

  /* DMA interrupt init */
  /* DMA1_Channel1_IRQn interrupt configuration */
  NVIC_SetPriority(DMA1_Channel1_IRQn, NVIC_EncodePriority(NVIC_GetPriorityGrouping(), 0, 0));
  NVIC_EnableIRQ(DMA1_Channel1_IRQn);
}

/**
 * @brief ADC1 Initialization Function
 * @param None
 * @retval None
 */
static void MX_ADC1_Init(void) {
  /* USER CODE BEGIN ADC1_Init 0 */

  /* USER CODE END ADC1_Init 0 */

  LL_ADC_InitTypeDef ADC_InitStruct = {0};
  LL_ADC_REG_InitTypeDef ADC_REG_InitStruct = {0};
  LL_ADC_CommonInitTypeDef ADC_CommonInitStruct = {0};

  /* Peripheral clock enable */
  LL_AHB2_GRP1_EnableClock(LL_AHB2_GRP1_PERIPH_ADC);

  /* ADC1 interrupt Init */
  NVIC_SetPriority(ADC1_2_IRQn, NVIC_EncodePriority(NVIC_GetPriorityGrouping(), 0, 0));
  NVIC_EnableIRQ(ADC1_2_IRQn);

  /* USER CODE BEGIN ADC1_Init 1 */

  /* USER CODE END ADC1_Init 1 */

  /** Common config
   */
  ADC_InitStruct.Resolution = LL_ADC_RESOLUTION_12B;
  ADC_InitStruct.DataAlignment = LL_ADC_DATA_ALIGN_RIGHT;
  ADC_InitStruct.LowPowerMode = LL_ADC_LP_MODE_NONE;
  LL_ADC_Init(ADC1, &ADC_InitStruct);
  ADC_REG_InitStruct.TriggerSource = LL_ADC_REG_TRIG_SOFTWARE;
  ADC_REG_InitStruct.SequencerLength = LL_ADC_REG_SEQ_SCAN_DISABLE;
  ADC_REG_InitStruct.SequencerDiscont = LL_ADC_REG_SEQ_DISCONT_DISABLE;
  ADC_REG_InitStruct.ContinuousMode = LL_ADC_REG_CONV_SINGLE;
  ADC_REG_InitStruct.DMATransfer = LL_ADC_REG_DMA_TRANSFER_LIMITED;
  ADC_REG_InitStruct.Overrun = LL_ADC_REG_OVR_DATA_PRESERVED;
  LL_ADC_REG_Init(ADC1, &ADC_REG_InitStruct);
  ADC_CommonInitStruct.CommonClock = LL_ADC_CLOCK_ASYNC_DIV1;
  ADC_CommonInitStruct.Multimode = LL_ADC_MULTI_INDEPENDENT;
  LL_ADC_CommonInit(__LL_ADC_COMMON_INSTANCE(ADC1), &ADC_CommonInitStruct);
  LL_ADC_SetCommonPathInternalCh(__LL_ADC_COMMON_INSTANCE(ADC1), LL_ADC_PATH_INTERNAL_NONE);

  /* Disable ADC deep power down (enabled by default after reset state) */
  LL_ADC_DisableDeepPowerDown(ADC1);
  /* Enable ADC internal voltage regulator */
  LL_ADC_EnableInternalRegulator(ADC1);
  /* Delay for ADC internal voltage regulator stabilization. */
  /* Compute number of CPU cycles to wait for, from delay in us. */
  /* Note: Variable divided by 2 to compensate partially */
  /* CPU processing cycles (depends on compilation optimization). */
  /* Note: If system core clock frequency is below 200kHz, wait time */
  /* is only a few CPU processing cycles. */
  volatile uint32_t wait_loop_index;
  wait_loop_index = ((LL_ADC_DELAY_INTERNAL_REGUL_STAB_US * (SystemCoreClock / (100000 * 2))) / 10);
  while (wait_loop_index != 0) {
    wait_loop_index--;
  }

  LL_DMA_SetPeriphRequest(DMA1, LL_DMA_CHANNEL_1, LL_DMA_REQUEST_0);
  LL_DMA_SetDataTransferDirection(DMA1, LL_DMA_CHANNEL_1, LL_DMA_DIRECTION_PERIPH_TO_MEMORY);
  LL_DMA_SetChannelPriorityLevel(DMA1, LL_DMA_CHANNEL_1, LL_DMA_PRIORITY_HIGH);
  LL_DMA_SetMode(DMA1, LL_DMA_CHANNEL_1, LL_DMA_MODE_NORMAL);
  LL_DMA_SetPeriphIncMode(DMA1, LL_DMA_CHANNEL_1, LL_DMA_PERIPH_NOINCREMENT);
  LL_DMA_SetMemoryIncMode(DMA1, LL_DMA_CHANNEL_1, LL_DMA_MEMORY_INCREMENT);
  LL_DMA_SetPeriphSize(DMA1, LL_DMA_CHANNEL_1, LL_DMA_PDATAALIGN_HALFWORD);
  LL_DMA_SetMemorySize(DMA1, LL_DMA_CHANNEL_1, LL_DMA_MDATAALIGN_WORD);
}

/**
 * @brief DAC1 Initialization Function
 * @param None
 * @retval None
 */
static void MX_DAC1_Init(void) {
  // Configure DAC1 channel 1 to output with normal mode, external pin, output buffer enabled.

  // DAC_ChannelConfTypeDef sConfig = {0};

  // Enable DAC clock
  RCC->APB1ENR1 |= RCC_APB1ENR1_DAC1EN;

  // Enable DAC channel 1
  DAC1->CR |= DAC_CR_EN1;

  // Disable DAC hardware trigger
  DAC1->CR &= ~DAC_CR_TEN1;

  // Set DAC trigger to software
  DAC1->CR &= ~DAC_CR_TSEL1;

  // Set DAC output to a midpoint voltage
  DAC1->DHR12R1 = (0x1ul << 11);
  // DAC1->DHR12R1 = 3971ul; // Set near supply voltage
  // DAC1->DHR12R1 = 124ul; // Set near ground

  // Trigger DAC
  DAC1->SWTRIGR |= DAC_SWTRIGR_SWTRIG1;

  // Settle
  HAL_Delay(10);
}

// STM's HAL opamp code unfortunately requires a global variable of this exact name.
OPAMP_HandleTypeDef hopamp1;
static void MX_OPAMP1_Init(void) {
  hopamp1.Instance = OPAMP1;
  hopamp1.Init.PowerSupplyRange = OPAMP_POWERSUPPLY_HIGH;
  hopamp1.Init.Mode = OPAMP_STANDALONE_MODE;
  hopamp1.Init.NonInvertingInput = OPAMP_NONINVERTINGINPUT_IO0;
  hopamp1.Init.InvertingInput = OPAMP_INVERTINGINPUT_IO0;
  hopamp1.Init.PowerMode = OPAMP_POWERMODE_NORMALPOWER;
  hopamp1.Init.UserTrimming = OPAMP_TRIMMING_FACTORY;
  if (HAL_OPAMP_Init(&hopamp1) != HAL_OK) {
    Error_Handler();
  }

  if (HAL_OPAMP_Start(&hopamp1) != HAL_OK) {
    Error_Handler();
  }
}

// STM's HAL opamp code unfortunately requires a global variable of this exact name.
OPAMP_HandleTypeDef hopamp2;
static void MX_OPAMP2_Init(void) {
  hopamp2.Instance = OPAMP2;
  hopamp2.Init.PowerSupplyRange = OPAMP_POWERSUPPLY_HIGH;
  hopamp2.Init.Mode = OPAMP_STANDALONE_MODE;
  hopamp2.Init.NonInvertingInput = OPAMP_NONINVERTINGINPUT_IO0;
  hopamp2.Init.InvertingInput = OPAMP_INVERTINGINPUT_IO0;
  hopamp2.Init.PowerMode = OPAMP_POWERMODE_NORMALPOWER;
  hopamp2.Init.UserTrimming = OPAMP_TRIMMING_FACTORY;
  if (HAL_OPAMP_Init(&hopamp2) != HAL_OK) {
    Error_Handler();
  }

  if (HAL_OPAMP_Start(&hopamp2) != HAL_OK) {
    Error_Handler();
  }
}

static void MX_TIM2_Init(void) {
  TIM_HandleTypeDef htim2;

  __HAL_RCC_TIM2_CLK_ENABLE();

  TIM_ClockConfigTypeDef sClockSourceConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};

  htim2.Instance = TIM2;
  htim2.Init.Prescaler = 0;
  htim2.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim2.Init.Period = 4294967295;
  htim2.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_Base_Init(&htim2) != HAL_OK) {
    Error_Handler();
  }
  sClockSourceConfig.ClockSource = TIM_CLOCKSOURCE_INTERNAL;
  if (HAL_TIM_ConfigClockSource(&htim2, &sClockSourceConfig) != HAL_OK) {
    Error_Handler();
  }
  if (HAL_TIM_OC_Init(&htim2) != HAL_OK) {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim2, &sMasterConfig) != HAL_OK) {
    Error_Handler();
  }
}

static void MX_TIM5_Init(void) {
  TIM_HandleTypeDef htim5;

  TIM_ClockConfigTypeDef sClockSourceConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};

  htim5.Instance = TIM5;
  htim5.Init.Prescaler = 0;
  htim5.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim5.Init.Period = 4294967295;
  htim5.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim5.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_Base_Init(&htim5) != HAL_OK) {
    Error_Handler();
  }
  sClockSourceConfig.ClockSource = TIM_CLOCKSOURCE_INTERNAL;
  if (HAL_TIM_ConfigClockSource(&htim5, &sClockSourceConfig) != HAL_OK) {
    Error_Handler();
  }
  if (HAL_TIM_OC_Init(&htim5) != HAL_OK) {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim5, &sMasterConfig) != HAL_OK) {
    Error_Handler();
  }
}

void Error_Reporter(void) {
  // Blink the status LED (PB13) to indicate an error.
  // Interrupts are left enabled: HAL_Delay relies on the SysTick interrupt.
  __HAL_RCC_GPIOB_CLK_ENABLE();

  GPIO_InitTypeDef gpio = {0};
  gpio.Pin = GPIO_PIN_13;
  gpio.Mode = GPIO_MODE_OUTPUT_PP;
  gpio.Pull = GPIO_NOPULL;
  gpio.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOB, &gpio);

  while (1) {
    HAL_GPIO_TogglePin(GPIOB, GPIO_PIN_13);
    HAL_Delay(100);
  }
}

#ifdef USE_FULL_ASSERT
/**
 * @brief  Reports the name of the source file and the source line number
 *         where the assert_param error has occurred.
 * @param  file: pointer to the source file name
 * @param  line: assert_param error line source number
 * @retval None
 */
void assert_failed(uint8_t* file, uint32_t line) {
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
