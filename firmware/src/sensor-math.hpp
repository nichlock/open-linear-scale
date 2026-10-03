#ifndef SENSOR_MATH_HPP
#define SENSOR_MATH_HPP

#include <stm32l4xx_hal.h>

namespace casm {

typedef int16_t rawtrans_t;
typedef float fixedtrans_t;

typedef fixedtrans_t fixedpos_t;

const static size_t EMITTER_PERIOD = 4;
const static size_t EMITTER_COUNT = 8;
const static size_t EMITTER_STATE_COUNT = 16;

// extern rawtrans_t readings[EMITTER_STATE_COUNT + 1][2];  // Plus one in case of an IRQ race condition
const static int16_t STACK_SMASH_MAGIC = 0xAAAAu;        ///< Value used to detect stack smashing from interrupts (may be possible in case of a certain race condition)

// TODO: convert this to an emitter state array and dynamically generate the BSRR values based on a pinmap
// This will allow the business logic of the emitter states to be seperate from the pin mapping
const static uint32_t emitter_states[EMITTER_STATE_COUNT] = {
    0x0F, 0xE1, 0x1E, 0xC3, 0x3C, 0x87, 0x78, 0x0F,  //
    0xF0, 0x1E, 0xE1, 0x3C, 0xC3, 0x78, 0x87, 0xF0   //
};

const static rawtrans_t RAWTRANS_MAX = INT16_MAX;
const static rawtrans_t RAWTRANS_MIN = INT16_MIN;

inline fixedpos_t fixedabs(fixedpos_t val) {
  // TODO: this is a crappy fix for the crappy fixed position number library I used.
  if (val < 0)
    val *= fixedpos_t(-1.0);
  return val;
}

fixedpos_t evalPosition(rawtrans_t readings[EMITTER_PERIOD][2]);

/**
 * @brief Based on current and previous results of evalPosition, determine the
 *        current absolute position.
 *
 * @param new_pos Latest incremental position read from evalPosition().
 * @param[inout] prev_pos_recieved Previous incremental position. Will be overwritten with new_pos upon completion.
 * @param[inout] current_full_position Previous full position estimate, will be overwritten with the new position.
 */
void updatePosition(casm::fixedtrans_t new_pos,
                    casm::fixedtrans_t& prev_pos_recieved,
                    casm::fixedtrans_t& current_full_position);
};  // namespace casm

#endif  // End of include guard for SENSOR_MATH_HPP