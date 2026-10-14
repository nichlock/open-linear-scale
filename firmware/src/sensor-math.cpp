#include "sensor-math.hpp"

#include <tgmath.h>

algo::fixedpos_t algo::evalPosition(adcreading_t readings[EMITTER_PERIOD][2]) {
  uint8_t lane, i;
  uint8_t first_sign;
  int8_t transition_idx;
  fixedtrans_t x1, x2, zeros[2], dist;

  for (lane = 0; lane < 2; lane++) {
    first_sign = readings[0][lane] >= 0;
    // Sets the default to 1 + (final element checked)
    transition_idx = (EMITTER_PERIOD);

    // if (REPORT_DIRECT_TRANSIENTS) {
    //   for (i = 0; i < EMITTER_PERIOD; i++) {
    //     Serial.print(readings[i][lane], DEC);
    //     Serial.print(",");
    //   }
    //   Serial.print(";");
    // }

    // Look for the first zero crossing and interpolate
    for (i = 0; i < EMITTER_PERIOD; i++) {
      if ((readings[i][lane] >= 0) != first_sign) {
        transition_idx = i;
        break;
      }
    }

    if (transition_idx == (EMITTER_PERIOD)) {
      // Handle waveforms that do not explicitly cross 0
      x1 = readings[EMITTER_PERIOD - 1][lane];
      x2 = -readings[0][lane];
    } else {
      x1 = readings[transition_idx - 1][lane];
      x2 = readings[transition_idx][lane];
    }

    zeros[lane] = -x1 / (x2 - x1);
    zeros[lane] += transition_idx;

    // Handle the lane offset
    if (lane) zeros[lane] -= 0.5;

    // Handle overflows above four
    if (zeros[lane] >= 4) {
      zeros[lane] -= 4;
    }
  }
  // if (REPORT_DIRECT_TRANSIENTS) {
  //   Serial.println();
  // }

  dist = zeros[0] - zeros[1];
  if (fabs(dist) > 3.75) {
    // Lanes disagree (one lane has overflowed but the other hasn't).
    // Averaging would choose a midpoint (ie. we'd get '2' when we're actually at 4 (=0)).
    // We'll just pick one and run with it.
    return zeros[0];
  }

  // If lanes agree, return the average
  return (zeros[0] + zeros[1]) / 2;
}

// algo::fixedtrans_t algo::updatePosition(algo::fixedtrans_t prev_abs_pos, algo::fixedtrans_t incremental_pos) {

// new_pos --> new, incremental
// prev_pos_recieved --> old, incremental
// current_full_position --> position to update
void algo::updatePosition(algo::fixedtrans_t new_pos,
                          algo::fixedtrans_t& prev_pos_recieved,
                          algo::fixedtrans_t& current_full_position) {
  static algo::fixedpos_t distance;

  distance = new_pos - prev_pos_recieved;  // Inverted to flip the positive movement direction

  // If the magnitude of the distance is near the max possible magnitude, we've
  // moved to a new period. Handle this by going up or down by the distance we
  // actually moved
  if (fabs(distance) > algo::EMITTER_PERIOD - 1) {
    if (distance < 0) {
      // Periodic value jumped from 0 to max, so we went backwards across periods
      current_full_position += (algo::fixedpos_t(algo::EMITTER_PERIOD) + distance);
    } else {
      current_full_position -= (algo::fixedpos_t(algo::EMITTER_PERIOD) - distance);
    }
  } else {
    current_full_position += distance;
  }
  prev_pos_recieved = new_pos;
}
