#include "hal/hal.h"
#include "display.h"
#include "input.h"

#include <Arduino.h>

namespace {

class Esp32P4_7BBoard : public hal::Board {
 public:
  bool init() override {
    Serial.println("[hal-esp32p4-7b] board stub — see ARCHITECTURE/firmware-hal.md");
    bool dispOk  = display_.init();
    bool inputOk = input_.init();
    return dispOk && inputOk;
  }

  hal::Display&     display() override { return display_; }
  hal::InputSource& input()   override { return input_; }

  // Phase B: PWM on the DSI backlight pin. Stub accepts and ignores.
  void backlight(uint8_t) override {}

 private:
  hal::esp32p4_7b::DisplayMipiDsi display_;
  hal::esp32p4_7b::InputTouch     input_;
};

Esp32P4_7BBoard g_board;

}  // namespace

namespace hal { Board& currentBoard() { return g_board; } }
