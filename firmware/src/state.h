#pragma once
//
// Shared firmware state.
//
// Globals defined in main.cpp, declared here so views.cpp can render from
// the same state main.cpp mutates. Concurrency: writes from gatewayTask
// (Core 0) take `stateMutex`; reads from loop()/views.cpp (Core 1) currently
// do not — same model as pre-refactor. If torn-read symptoms appear, the
// fix is to lock around the read in `redrawCurrentView`, not here.

#include <Arduino.h>
#include <time.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

#include "config.h"

enum ViewMode { VIEW_CLOCK = 0, VIEW_HISTORY = 1, VIEW_COUNTER = 2 };

struct FeedSession {
  time_t startEpoch = 0;
  time_t stopEpoch  = 0;
};

static constexpr size_t HISTORY_SIZE = 8;

struct ActiveCounter {
  bool     active                = false;
  String   title;
  String   subtitle;
  uint32_t baseElapsedSeconds    = 0;
  uint32_t startedAtMs           = 0;
};

extern ViewMode           currentView;
extern FeedSession        feedHistory[HISTORY_SIZE];
extern size_t             feedHistoryCount;
extern size_t             feedHistoryHead;
extern ActiveCounter      activeCounter;
extern volatile bool      gatewayOnline;
extern SemaphoreHandle_t  stateMutex;

inline bool gatewayMode() { return GATEWAY_URL[0] != '\0'; }

// Time + string helpers used by views (defined in main.cpp).
String currentTimestamp();
String formatElapsed(uint32_t seconds);
bool   getClockText(String& out);
bool   getDateText(String& out);
