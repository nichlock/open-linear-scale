#ifndef FILTERS_HPP
#define FILTERS_HPP

#include <stdint.h>

#include <array>

template <typename T>
class Filter {
 public:
  Filter() {}
  virtual ~Filter() {}
  virtual T filter(T input) { return input; }
};

/**
 * @brief First-order recursive filter, equivilent to an RC filter.
 *
 * Very fast in operation as it only uses shifts, addition, and subtraction.
 *
 * The 3db point of this filter can be found by:
 * \log_{1-2^{-k}}0.5
 *
 * In fact, any db can be entered in place of 0.5.
 *
 * Example values and their 3db points:
 * k = 5: 88.4 iterations
 * k = 5: 44.0 iterations
 * k = 5: 21.8 iterations
 * k = 4: 10.7 iterations
 * k = 3:  5.2 iterations
 * k = 2:  2.4 iterations
 * k = 1:  1.0 iteration exactly
 *
 * @tparam T      The input/output datatype.
 * @tparam long_T A type where sizeof(long_T) == 2 * sizeof(T)
 * @tparam k      The rate of the filter.
 */
template <typename T, typename long_T, int k>
class FastLpf_T : public Filter<T> {
 private:
  long_T reg;

 public:
  FastLpf_T() { this->reg = 0; }
  T filter(T input) {
    this->reg = this->reg - (this->reg >> k) + (long_T)input;
    return this->reg >> k;
  }
};

template <int k>
using FastLpf_8 = FastLpf_T<int8_t, int16_t, k>;

template <int k>
using FastLpf_16 = FastLpf_T<int16_t, int32_t, k>;

template <int k>
using FastLpf_32 = FastLpf_T<int32_t, int64_t, k>;

template <int k>
using FastLpf_u8 = FastLpf_T<uint8_t, uint16_t, k>;

template <int k>
using FastLpf_u16 = FastLpf_T<uint16_t, uint32_t, k>;

template <int k>
using FastLpf_u32 = FastLpf_T<uint32_t, uint64_t, k>;

/**
 * @brief Generic IIR filter.
 *
 */
template <typename T, int k>
class Iir_T : public Filter<T> {
 private:
  std::array<T, k> b, a;
  std::array<T, k> x, y;

  uint32_t roll_idx;

 public:
  Iir_T(std::array<T, k> b, std::array<T, k> a) : b(b), a(a) {
    roll_idx = 0;
    for (int i = 0; i < k; i++) {
      x[i] = 0;
      y[i] = 0;
    }
  }

  T filter(T input) {
    x[roll_idx] = input;
    y[roll_idx] = 0;
    for (int i = 0; i < k; i++) {
      y[roll_idx] += b[i] * x[(roll_idx + i) % k];
    }
    for (int i = 1; i < k; i++) {
      y[roll_idx] -= a[i] * y[(roll_idx + i) % k];
    }

    y[roll_idx] /= a[0];

    T ret = y[roll_idx];

    roll_idx = roll_idx ? roll_idx - 1 : k - 1;

    return ret;
  }
};

/**
 * @brief Generic Moving Average filter.
 *
 */
template <typename T, int k>
class MovingAverage_T : public Filter<T> {
 private:
  std::array<T, k> mem;

  T sum;

  uint32_t roll_idx;

 public:
  MovingAverage_T() {
    sum = 0;
    roll_idx = 0;
    for (int i = 0; i < k; i++) {
      mem[i] = 0;
    }
  }

  T filter(T input) {
    sum -= mem[roll_idx];
    sum += input;
    mem[roll_idx] = input;

    roll_idx = roll_idx ? roll_idx - 1 : k - 1;

    return sum / k;
  }
};

#endif  // End of include guard for FILTERS_HPP
