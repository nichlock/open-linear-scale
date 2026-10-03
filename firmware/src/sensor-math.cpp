#include "sensor-math.hpp"

casm::fixedpos_t casm::evalPosition(rawtrans_t readings[EMITTER_PERIOD][2]) {
  uint8_t phase, i;
  uint8_t first_sign;
  int8_t transition_idx;
  fixedtrans_t x1, x2, zeros[2], dist;

  for (phase = 0; phase < 2; phase++) {
    first_sign = readings[0][phase] >= 0;
    // Sets the default to 1 + (final element checked)
    transition_idx = (EMITTER_PERIOD);

    // if (REPORT_DIRECT_TRANSIENTS) {
    //   for (i = 0; i < EMITTER_PERIOD; i++) {
    //     Serial.print(readings[i][phase], DEC);
    //     Serial.print(",");
    //   }
    //   Serial.print(";");
    // }

    // Look for the first zero crossing and interpolate
    for (i = 0; i < EMITTER_PERIOD; i++) {
      if ((readings[i][phase] >= 0) != first_sign) {
        transition_idx = i;
        break;
      }
    }

    if (transition_idx == (EMITTER_PERIOD)) {
      // Handle waveforms that do not explicitly cross 0
      x1 = readings[EMITTER_PERIOD - 1][phase];
      x2 = -readings[0][phase];
    } else {
      x1 = readings[transition_idx - 1][phase];
      x2 = readings[transition_idx][phase];
    }

    zeros[phase] = -x1 / (x2 - x1);
    zeros[phase] += transition_idx;

    // Handle the phase shift
    if (phase) zeros[phase] -= 0.5;

    // Handle overflows above four
    if (zeros[phase] >= 4) {
      zeros[phase] -= 4;
    }
  }
  // if (REPORT_DIRECT_TRANSIENTS) {
  //   Serial.println();
  // }

  dist = zeros[0] - zeros[1];
  if (fixedabs(dist) > 3.75) {
    // Phases disagree (one phase has overflowed but the other hasn't).
    // Averaging would choose a midpoint (ie. we'd get '2' when we're actually at 4 (=0)).
    // We'll just pick one and run with it.
    return zeros[0];
  }

  // If phases agree, return the average
  return (zeros[0] + zeros[1]) / 2;
}

// casm::fixedtrans_t casm::updatePosition(casm::fixedtrans_t prev_abs_pos, casm::fixedtrans_t incremental_pos) {

// new_pos --> new, incremental
// prev_pos_recieved --> old, incremental
// current_full_position --> position to update
void casm::updatePosition(casm::fixedtrans_t new_pos,
                          casm::fixedtrans_t& prev_pos_recieved,
                          casm::fixedtrans_t& current_full_position) {
  static casm::fixedpos_t distance;

  distance = new_pos - prev_pos_recieved;  // Inverted to flip the positive movement direction

  // If the magnitude of the distance is near the max possible magnitude, we've
  // moved to a new period. Handle this by going up or down by the distance we
  // actually moved
  if (casm::fixedabs(distance) > casm::EMITTER_PERIOD - 1) {
    if (distance < 0) {
      // Periodic value jumped from 0 to max, so we went backwards across periods
      current_full_position += (casm::fixedpos_t(casm::EMITTER_PERIOD) + distance);
    } else {
      current_full_position -= (casm::fixedpos_t(casm::EMITTER_PERIOD) - distance);
    }
  } else {
    current_full_position += distance;
  }
  prev_pos_recieved = new_pos;
}