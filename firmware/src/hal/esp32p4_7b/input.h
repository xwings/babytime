#pragma once
#include "hal/hal.h"

namespace hal::esp32p4_7b {

// Stub: 7B board has GT911 capacitive touch (no physical buttons). Phase B
// will register callbacks against two on-screen regions (cycle / toggle).
// Today the callbacks are stored but never fired.
class InputTouch : public InputSource {
 public:
  bool init();

  void onPrimaryAction(ActionCallback cb)   override { primary_   = cb; }
  void onSecondaryAction(ActionCallback cb) override { secondary_ = cb; }

  void poll() override {}

 private:
  ActionCallback primary_   = nullptr;
  ActionCallback secondary_ = nullptr;
};

}  // namespace hal::esp32p4_7b
