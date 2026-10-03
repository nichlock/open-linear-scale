#ifndef REGISTERS_HPP
#define REGISTERS_HPP

#include <cstdint>

// Bounds- and permission-checked register access. Register storage itself
// (registers[], permissions[], RegIndex) is private to measure-main-events.cpp.
bool writeRegisterChecked(uint32_t idx, uint32_t value);
bool readRegisterChecked(uint32_t idx, uint32_t* out);

#endif  // REGISTERS_HPP
