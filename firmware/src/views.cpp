#include "views.h"
#include "state.h"
#include "hal/hal.h"

#include <WiFi.h>
#include <time.h>

namespace {

using hal::Color;
using hal::Display;
using hal::FontFamily;
using hal::TextStyle;

// ---- Seven-segment renderer ------------------------------------------------
// Pure fillRect math; size/spacing are caller-supplied so we can scale per
// display in the future. Layout matches the pre-HAL 320×240 numbers when the
// caller passes those defaults.

constexpr int DIGIT_W       = 50;
constexpr int DIGIT_H       = 150;
constexpr int SEG_THICKNESS = 8;
constexpr int CHAR_GAP      = 16;
constexpr int COLON_W       = 14;

void drawDigit(Display& d, int x, int y, int digit, Color color) {
  static const bool segments[10][7] = {
    {true, true, true, true, true, true, false},
    {false, true, true, false, false, false, false},
    {true, true, false, true, true, false, true},
    {true, true, true, true, false, false, true},
    {false, true, true, false, false, true, true},
    {true, false, true, true, false, true, true},
    {true, false, true, true, true, true, true},
    {true, true, true, false, false, false, false},
    {true, true, true, true, true, true, true},
    {true, true, true, true, false, true, true},
  };
  if (digit < 0 || digit > 9) return;
  const int t = SEG_THICKNESS;
  const int w = DIGIT_W;
  const int h = DIGIT_H;
  const int horizontalW = w - (2 * t);
  const int upperH = (h - (3 * t)) / 2;
  const int middleY = y + t + upperH;
  const int lowerY  = middleY + t;
  const int lowerH  = h - (3 * t) - upperH;
  if (segments[digit][0]) d.fillRect(x + t,     y,             horizontalW, t,      color);
  if (segments[digit][1]) d.fillRect(x + w - t, y + t,         t,           upperH, color);
  if (segments[digit][2]) d.fillRect(x + w - t, lowerY,        t,           lowerH, color);
  if (segments[digit][3]) d.fillRect(x + t,     y + h - t,     horizontalW, t,      color);
  if (segments[digit][4]) d.fillRect(x,         lowerY,        t,           lowerH, color);
  if (segments[digit][5]) d.fillRect(x,         y + t,         t,           upperH, color);
  if (segments[digit][6]) d.fillRect(x + t,     middleY,       horizontalW, t,      color);
}

void drawColon(Display& d, int x, int y, Color color) {
  const int dot     = SEG_THICKNESS + 2;
  const int dotX    = x + ((COLON_W - dot) / 2);
  const int centerY = y + (DIGIT_H / 2);
  const int offset  = DIGIT_H / 4;
  d.fillRect(dotX, centerY - offset, dot, dot, color);
  d.fillRect(dotX, centerY + offset - dot, dot, dot, color);
}

// Heartbeat: 500 ms on / 500 ms off, one full blink per second. Callers
// redraw at 500 ms cadence so the colon's animation lines up.
void drawBigDigits(Display& d, const String& text, int y,
                   Color hourColor, Color colonColor, Color minuteColor) {
  int totalWidth = 0;
  for (size_t i = 0; i < text.length(); i++) {
    totalWidth += (text.charAt(i) == ':') ? COLON_W : DIGIT_W;
    if (i + 1 < text.length()) totalWidth += CHAR_GAP;
  }
  // Bright orange MM weighs more than dark red HH; nudge left so the optical
  // center sits at the midline.
  int x = ((d.width() - totalWidth) / 2) - 16;
  if (x < 0) x = 0;
  bool showColon = ((millis() / 500) & 1U) == 0;
  int section = 0;  // 0 = HH, 1 = MM
  for (size_t i = 0; i < text.length(); i++) {
    char c = text.charAt(i);
    if (c == ':') {
      if (showColon) drawColon(d, x, y, colonColor);
      x += COLON_W + CHAR_GAP;
      if (section < 1) section++;
    } else {
      Color color = (section == 0) ? hourColor : minuteColor;
      drawDigit(d, x, y, c - '0', color);
      x += DIGIT_W + CHAR_GAP;
    }
  }
}

// ---- Layout helpers --------------------------------------------------------
// Footer Y is "near the bottom, leave room for one line of size-1 text."
// Bottom edge minus 14 matches the pre-HAL numbers (240 - 14 = 226).
inline int footerY(const Display& d) { return d.height() - 14; }

void drawFooterHint(Display& d, const char* hint) {
  d.drawText(14, footerY(d), hint,
             {hal::COLOR_DARKGREY, FontFamily::Ascii, 1});
}

const char* buttonHint() {
  return "K2 feed  K1 next";
}

const char* counterHint() {
  return "K2 toggle  K1 next";
}

const char* historyHint() {
  return "K1 next";
}

}  // namespace

// ---- Public ----------------------------------------------------------------

void drawStatus(const String& title, const String& body) {
  Display& d = hal::currentBoard().display();
  d.clear(hal::COLOR_BLACK);
  d.drawText(12, 12, title.c_str(), {hal::COLOR_CYAN,  FontFamily::Ascii, 2});
  d.drawText(12, 50, body.c_str(),  {hal::COLOR_WHITE, FontFamily::Ascii, 2});
  drawFooterHint(d, buttonHint());
  d.flush();
}

void drawClockScreen() {
  Display& d = hal::currentBoard().display();
  String clock;
  bool synced = getClockText(clock);

  d.clear(hal::COLOR_BLACK);
  d.drawText(14, 12, synced ? "Time" : "Syncing time...",
             {hal::COLOR_CYAN, FontFamily::Ascii, 2});

  String date;
  if (getDateText(date)) {
    int w = d.measureText(date.c_str(), FontFamily::Ascii, 2);
    int x = d.width() - w - 14;
    if (x < 0) x = 0;
    d.drawText(x, 12, date.c_str(), {hal::COLOR_YELLOW, FontFamily::Ascii, 2});
  }

  if (synced) {
    drawBigDigits(d, clock, 50, hal::COLOR_RED, hal::COLOR_WHITE, hal::COLOR_ORANGE);
  }

  // Footer-2: IP + gateway status, one line above the button hint.
  const int statusY = d.height() - 30;
  String ip = WiFi.localIP().toString();
  d.drawText(14, statusY, ip.c_str(), {hal::COLOR_DARKGREY, FontFamily::Ascii, 1});
  if (gatewayMode()) {
    int gx = 14 + d.measureText(ip.c_str(), FontFamily::Ascii, 1) + 6;
    d.drawText(gx, statusY, "gateway:", {hal::COLOR_DARKGREY, FontFamily::Ascii, 1});
    int sx = gx + d.measureText("gateway:", FontFamily::Ascii, 1);
    const char* word = gatewayOnline ? "online" : "offline";
    Color tone = gatewayOnline ? hal::COLOR_GREEN : hal::COLOR_RED;
    d.drawText(sx, statusY, word, {tone, FontFamily::Ascii, 1});
  }

  drawFooterHint(d, buttonHint());
  d.flush();
}

void drawCounter(uint32_t elapsedSeconds) {
  Display& d = hal::currentBoard().display();
  d.clear(hal::COLOR_BLACK);

  // Centered title: ASCII title + (optional) CJK subtitle, baseline-aligned.
  int titleW = d.measureText(activeCounter.title.c_str(), FontFamily::Ascii, 2);
  bool hasSub = activeCounter.subtitle.length() > 0;
  int subW = hasSub ? d.measureText(activeCounter.subtitle.c_str(),
                                    FontFamily::CjkMixed, 2)
                    : 0;
  int gap = hasSub ? 12 : 0;
  int totalW = titleW + gap + subW;
  int hx = (d.width() - totalW) / 2;
  if (hx < 0) hx = 0;

  d.drawText(hx, 8, activeCounter.title.c_str(),
             {hal::COLOR_YELLOW, FontFamily::Ascii, 2});
  if (hasSub) {
    d.drawText(hx + titleW + gap, 24, activeCounter.subtitle.c_str(),
               {hal::COLOR_YELLOW, FontFamily::CjkMixed, 2});
  }

  // Today's feeding tally, centered between the title and the big digits.
  char today[40];
  snprintf(today, sizeof(today), "Today: %d feeds  %d ml", todayFeeds, todayMl);
  int todayW = d.measureText(today, FontFamily::Ascii, 1);
  int tx = (d.width() - todayW) / 2;
  if (tx < 0) tx = 0;
  d.drawText(tx, 40, today, {hal::COLOR_GREEN, FontFamily::Ascii, 1});

  drawBigDigits(d, formatElapsed(elapsedSeconds), 50,
                hal::COLOR_RED, hal::COLOR_WHITE, hal::COLOR_ORANGE);

  String stamp = currentTimestamp();
  if (stamp.length() > 0) {
    int w = d.measureText(stamp.c_str(), FontFamily::Ascii, 2);
    int x = d.width() - w - 8;
    if (x < 0) x = 0;
    d.drawText(x, d.height() - 32, stamp.c_str(),
               {hal::COLOR_WHITE, FontFamily::Ascii, 2});
  }

  // Counter view uses a 2-px deeper footer to clear the timestamp baseline.
  d.drawText(14, d.height() - 12, counterHint(),
             {hal::COLOR_DARKGREY, FontFamily::Ascii, 1});
  d.flush();
}

void drawHistoryScreen() {
  Display& d = hal::currentBoard().display();
  d.clear(hal::COLOR_BLACK);
  d.drawText(14, 8, "Activity", {hal::COLOR_CYAN, FontFamily::Ascii, 2});

  if (feedHistoryCount == 0) {
    d.drawText(14, 50, "No records yet.",
               {hal::COLOR_DARKGREY, FontFamily::Ascii, 2});
  } else {
    const int lineH = 18;
    const int maxY  = d.height() - 22;  // leave one line for the footer
    int y = 32;
    char prevDate[16] = "";
    for (size_t i = 0; i < feedHistoryCount; i++) {
      size_t idx = (feedHistoryHead + HISTORY_SIZE - 1 - i) % HISTORY_SIZE;
      const FeedSession& s = feedHistory[idx];
      struct tm tmStart;
      localtime_r(&s.startEpoch, &tmStart);

      char dateStr[16];
      snprintf(dateStr, sizeof(dateStr), "%04d-%02d-%02d",
               tmStart.tm_year + 1900, tmStart.tm_mon + 1, tmStart.tm_mday);
      if (strcmp(dateStr, prevDate) != 0) {
        if (y + lineH > maxY) break;
        d.drawText(14, y, dateStr, {hal::COLOR_YELLOW, FontFamily::Ascii, 2});
        // Day's feeding volume, right-aligned on the date row. Only feeding
        // carries ml, so this is the day's total intake.
        int dayMl = 0;
        for (size_t j = i; j < feedHistoryCount; j++) {
          size_t jdx = (feedHistoryHead + HISTORY_SIZE - 1 - j) % HISTORY_SIZE;
          struct tm tmJ;
          localtime_r(&feedHistory[jdx].startEpoch, &tmJ);
          char ds[16];
          snprintf(ds, sizeof(ds), "%04d-%02d-%02d",
                   tmJ.tm_year + 1900, tmJ.tm_mon + 1, tmJ.tm_mday);
          if (strcmp(ds, dateStr) != 0) break;
          dayMl += feedHistory[jdx].volumeMl;
        }
        if (dayMl > 0) {
          char mlStr[16];
          snprintf(mlStr, sizeof(mlStr), "%dml", dayMl);
          int w = d.measureText(mlStr, FontFamily::Ascii, 2);
          int mx = d.width() - w - 14;
          if (mx < 0) mx = 0;
          d.drawText(mx, y, mlStr, {hal::COLOR_ORANGE, FontFamily::Ascii, 2});
        }
        y += lineH;
        strcpy(prevDate, dateStr);
      }

      char line[48];
      const char* act = s.activity[0] ? s.activity : "?";
      if (s.stopEpoch == 0) {
        snprintf(line, sizeof(line), "%02d:%02d-...  %s",
                 tmStart.tm_hour, tmStart.tm_min, act);
      } else {
        struct tm tmStop;
        localtime_r(&s.stopEpoch, &tmStop);
        snprintf(line, sizeof(line), "%02d:%02d-%02d:%02d %s",
                 tmStart.tm_hour, tmStart.tm_min,
                 tmStop.tm_hour,  tmStop.tm_min, act);
      }
      if (y + lineH > maxY) break;
      Color rowColor = (s.stopEpoch == 0) ? hal::COLOR_YELLOW : hal::COLOR_WHITE;
      d.drawText(24, y, line, {rowColor, FontFamily::Ascii, 2});
      y += lineH;
    }
  }

  drawFooterHint(d, historyHint());
  d.flush();
}

void redrawCurrentView() {
  switch (currentView) {
    case VIEW_HISTORY:
      drawHistoryScreen();
      break;
    case VIEW_COUNTER:
      if (activeCounter.active) {
        uint32_t elapsed = activeCounter.baseElapsedSeconds +
                           ((millis() - activeCounter.startedAtMs) / 1000);
        drawCounter(elapsed);
      } else {
        currentView = VIEW_CLOCK;
        drawClockScreen();
      }
      break;
    case VIEW_CLOCK:
    default:
      drawClockScreen();
      break;
  }
}
