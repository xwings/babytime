#pragma once
#include "hal/hal.h"

namespace hal::dnesp32s3b {

// Two buttons via XL9555 I/O expander on I²C (`0x20`):
//   P0.3 = K2          → SecondaryAction (toggle feeding)
//   P0.4 = K1 short    → PrimaryAction   (cycle view)
//   P0.4 = K1 long     → SyncRequest     (manual sync, ≥1500 ms hold)
//
// Polled at ~60 ms cadence with 80 ms edge debounce. The XL9555 must
// already be live (Wire.begin() + backlight init done) before `init()`
// runs; that's Board::init's responsibility.
class InputXl9555 : public InputSource {
 public:
  bool init();

  void onPrimaryAction(ActionCallback cb)   override { primary_   = cb; }
  void onSecondaryAction(ActionCallback cb) override { secondary_ = cb; }
  void onSyncRequest(ActionCallback cb)     override { sync_      = cb; }

  void poll() override;

 private:
  struct ButtonState {
    bool     pressed       = false;
    uint32_t lastChangeMs  = 0;
    uint32_t pressStartMs  = 0;
    bool     longFired     = false;
  };

  void handleShortOrLong(ButtonState& b, bool pressed,
                         ActionCallback shortCb, ActionCallback longCb,
                         uint32_t longMs);
  void handleRelease(ButtonState& b, bool pressed, ActionCallback releaseCb);

  ActionCallback primary_   = nullptr;
  ActionCallback secondary_ = nullptr;
  ActionCallback sync_      = nullptr;

  ButtonState k1_;
  ButtonState k2_;
  uint32_t    lastPollMs_ = 0;
  bool        ready_      = false;
};

}  // namespace hal::dnesp32s3b
