#pragma once
//
// View rendering. Each function paints one screen using HAL primitives;
// layout is computed from display.width()/height() so the same code targets
// both the DNESP32S3B (320×240) and the ESP32-P4-7B (1024×600) without
// per-board branches.

#include <Arduino.h>
#include <stdint.h>

void drawStatus(const String& title, const String& body);
void drawClockScreen();
void drawCounter(uint32_t elapsedSeconds);
void drawHistoryScreen();

void redrawCurrentView();
