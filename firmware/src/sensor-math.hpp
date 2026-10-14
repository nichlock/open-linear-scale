#ifndef SENSOR_MATH_HPP
#define SENSOR_MATH_HPP

#include <stm32l4xx_hal.h>

namespace algo {

typedef int32_t adcreading_t;

typedef float fixedtrans_t;
typedef fixedtrans_t fixedpos_t;

const static size_t EMITTER_PERIOD = 4;
const static size_t EMITTER_COUNT = 8;
const static size_t EMITTER_STATE_COUNT = 16;

const static uint32_t emitter_states[EMITTER_STATE_COUNT] = {
    0x0F, 0xE1, 0x1E, 0xC3, 0x3C, 0x87, 0x78, 0x0F,
    0xF0, 0x1E, 0xE1, 0x3C, 0xC3, 0x78, 0x87, 0xF0};

fixedpos_t evalPosition(adcreading_t readings[EMITTER_PERIOD][2]);

/**
 * @brief Based on current and previous results of evalPosition, determine the
 *        current absolute position.
 *
 * @param new_pos Latest incremental position read from evalPosition().
 * @param[inout] prev_pos_recieved Previous incremental position. Will be overwritten with new_pos upon completion.
 * @param[inout] current_full_position Previous full position estimate, will be overwritten with the new position.
 */
void updatePosition(algo::fixedtrans_t new_pos,
                    algo::fixedtrans_t& prev_pos_recieved,
                    algo::fixedtrans_t& current_full_position);
};  // namespace algo

#endif  // End of include guard for SENSOR_MATH_HPP