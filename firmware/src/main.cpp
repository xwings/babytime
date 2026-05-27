// babytime — firmware entry point.
//
// Holds app state (feed history, active counter, pending event queue),
// the gateway HTTP client (runs on Core 0 via gatewayTask), NTP setup,
// view orchestration, and the three semantic-action handlers. All
// board-specific pin pushing lives behind the HAL in hal/<board>/.
#include <Arduino.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <NetworkClientSecure.h>
#include <WiFi.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <freertos/task.h>
#include <time.h>

#include "config.h"
#include "hal/hal.h"
#include "state.h"
#include "views.h"

// ---------------------------------------------------------------------------
// Shared state (declared extern in state.h, defined here)
// ---------------------------------------------------------------------------

ViewMode           currentView      = VIEW_CLOCK;
FeedSession        feedHistory[HISTORY_SIZE];
size_t             feedHistoryCount = 0;
size_t             feedHistoryHead  = 0;
ActiveCounter      activeCounter;
volatile bool      gatewayOnline    = true;
SemaphoreHandle_t  stateMutex       = nullptr;

namespace {

uint32_t      lastCounterDrawMs = 0;
uint32_t      lastClockDrawMs   = 0;
bool          feedingActive     = false;
volatile bool gatewayStateDirty = false;

constexpr uint32_t K1_LONG_PRESS_MS = 1500;  // referenced by docs; HAL owns timing

// ---- Pending event queue (Core 1 producer, Core 0 consumer) ---------------

struct PendingEvent {
  char   type[8];
  time_t epoch;
};
constexpr size_t PENDING_QUEUE_SIZE = 16;
PendingEvent pendingQueue[PENDING_QUEUE_SIZE];
size_t       pendingCount = 0;

void recordFeedStart() {
  time_t now;
  time(&now);
  FeedSession s;
  s.startEpoch = now;
  s.stopEpoch  = 0;
  feedHistory[feedHistoryHead] = s;
  feedHistoryHead = (feedHistoryHead + 1) % HISTORY_SIZE;
  if (feedHistoryCount < HISTORY_SIZE) feedHistoryCount++;
}

void recordFeedStop() {
  if (feedHistoryCount == 0) return;
  size_t lastIdx = (feedHistoryHead + HISTORY_SIZE - 1) % HISTORY_SIZE;
  time_t now;
  time(&now);
  feedHistory[lastIdx].stopEpoch = now;
}

void enqueuePendingEvent(const char* type, time_t epoch) {
  xSemaphoreTake(stateMutex, portMAX_DELAY);
  if (pendingCount >= PENDING_QUEUE_SIZE) {
    for (size_t i = 1; i < pendingCount; i++) pendingQueue[i - 1] = pendingQueue[i];
    pendingCount--;
  }
  strncpy(pendingQueue[pendingCount].type, type,
          sizeof(pendingQueue[pendingCount].type) - 1);
  pendingQueue[pendingCount].type[sizeof(pendingQueue[pendingCount].type) - 1] = 0;
  pendingQueue[pendingCount].epoch = epoch;
  pendingCount++;
  xSemaphoreGive(stateMutex);
}

// ---- Counter helper -------------------------------------------------------

void setCounter(const String& title, const String& subtitle = "",
                uint32_t baseElapsedSeconds = 0) {
  activeCounter.active             = true;
  activeCounter.title              = title;
  activeCounter.subtitle           = subtitle;
  activeCounter.baseElapsedSeconds = baseElapsedSeconds;
  activeCounter.startedAtMs        = millis();
  lastCounterDrawMs                = 0;
  currentView                      = VIEW_COUNTER;
  drawCounter(baseElapsedSeconds);
}

// ---- Gateway HTTP client (runs on Core 0 via gatewayTask) -----------------

String gatewayUrl(const char* path) {
  String base = String(GATEWAY_URL);
  if (base.endsWith("/")) base.remove(base.length() - 1);
  return base + path;
}

// HTTPClient and (for https) the underlying secure transport share scope:
// the secure client must outlive any active HTTP request.
struct HttpSession {
  HTTPClient            http;
  NetworkClientSecure   secureClient;
};

bool beginHttp(HttpSession& s, const String& url, uint32_t timeoutMs) {
  s.http.setTimeout(timeoutMs);
  if (url.startsWith("https://")) {
#ifdef GATEWAY_CA_CERT
    s.secureClient.setCACert(GATEWAY_CA_CERT);
#else
    s.secureClient.setInsecure();
#endif
    if (!s.http.begin(s.secureClient, url)) return false;
  } else {
    if (!s.http.begin(url)) return false;
  }
  if (strlen(GATEWAY_TOKEN) > 0) {
    s.http.addHeader("Authorization", String("Bearer ") + GATEWAY_TOKEN);
  }
  return true;
}

bool gatewayPostEvent(const PendingEvent& ev) {
  if (WiFi.status() != WL_CONNECTED) return false;
  HttpSession s;
  if (!beginHttp(s, gatewayUrl("/api/events"), 3000)) return false;
  s.http.addHeader("Content-Type", "application/json");
  JsonDocument doc;
  doc["type"]            = ev.type;
  doc["device_id"]       = DEVICE_ID;
  doc["timestamp_epoch"] = (long)ev.epoch;
  String body;
  serializeJson(doc, body);
  int status = s.http.POST(body);
  s.http.end();
  return status >= 200 && status < 300;
}

void applyGatewayState(JsonDocument& doc) {
  xSemaphoreTake(stateMutex, portMAX_DELAY);

  // Don't overwrite if we still have unsent events; we're ahead of the gateway.
  if (pendingCount > 0) {
    xSemaphoreGive(stateMutex);
    return;
  }

  time_t now;
  time(&now);

  JsonVariant active = doc["active"];
  feedingActive = !active.isNull();

  feedHistoryCount = 0;
  feedHistoryHead  = 0;
  JsonArray history = doc["history"].as<JsonArray>();
  size_t n = history.size();
  for (size_t i = 0; i < n; i++) {
    size_t srcIdx = n - 1 - i;  // gateway returns newest-first
    JsonObject r = history[srcIdx];
    FeedSession s;
    s.startEpoch = (time_t)(long)r["start_epoch"];
    JsonVariant stop = r["stop_epoch"];
    s.stopEpoch = stop.isNull() ? 0 : (time_t)(long)stop;
    feedHistory[feedHistoryHead] = s;
    feedHistoryHead = (feedHistoryHead + 1) % HISTORY_SIZE;
    if (feedHistoryCount < HISTORY_SIZE) feedHistoryCount++;
  }

  if (feedingActive) {
    JsonObject act = active.as<JsonObject>();
    time_t startEpoch = (time_t)(long)act["start_epoch"];
    activeCounter.active             = true;
    activeCounter.title              = "Feeding now";
    activeCounter.subtitle           = "开始喂养";
    activeCounter.baseElapsedSeconds = (now > startEpoch) ? (uint32_t)(now - startEpoch) : 0;
    activeCounter.startedAtMs        = millis();
  } else if (feedHistoryCount > 0) {
    size_t lastIdx = (feedHistoryHead + HISTORY_SIZE - 1) % HISTORY_SIZE;
    const FeedSession& s = feedHistory[lastIdx];
    if (s.stopEpoch != 0) {
      activeCounter.active             = true;
      activeCounter.title              = "Last fed";
      activeCounter.subtitle           = "结束喂养";
      activeCounter.baseElapsedSeconds = (now > s.stopEpoch) ? (uint32_t)(now - s.stopEpoch) : 0;
      activeCounter.startedAtMs        = millis();
    }
  } else {
    activeCounter.active = false;
  }

  gatewayStateDirty = true;
  xSemaphoreGive(stateMutex);
}

bool gatewayFetchState() {
  if (WiFi.status() != WL_CONNECTED) return false;
  HttpSession s;
  if (!beginHttp(s, gatewayUrl("/api/state"), 3000)) return false;
  int status = s.http.GET();
  if (status < 200 || status >= 300) {
    s.http.end();
    return false;
  }
  String body = s.http.getString();
  s.http.end();
  JsonDocument doc;
  if (deserializeJson(doc, body)) return false;
  applyGatewayState(doc);
  return true;
}

void drainPendingQueue() {
  while (true) {
    PendingEvent ev;
    bool have = false;
    xSemaphoreTake(stateMutex, portMAX_DELAY);
    if (pendingCount > 0) {
      ev = pendingQueue[0];
      have = true;
    }
    xSemaphoreGive(stateMutex);
    if (!have) return;
    if (!gatewayPostEvent(ev)) return;
    xSemaphoreTake(stateMutex, portMAX_DELAY);
    if (pendingCount > 0) {
      for (size_t i = 1; i < pendingCount; i++) pendingQueue[i - 1] = pendingQueue[i];
      pendingCount--;
    }
    xSemaphoreGive(stateMutex);
  }
}

void gatewayTask(void*) {
  while (true) {
    if (gatewayMode() && WiFi.status() == WL_CONNECTED) {
      drainPendingQueue();
      gatewayOnline = gatewayFetchState();
    }
    vTaskDelay(pdMS_TO_TICKS(GATEWAY_POLL_MS));
  }
}

// ---- Semantic action handlers (wired to InputSource callbacks) ------------

void cycleView() {
  for (int i = 0; i < 3; i++) {
    currentView = (ViewMode)((currentView + 1) % 3);
    if (currentView == VIEW_COUNTER && !activeCounter.active) continue;
    break;
  }
  redrawCurrentView();
}

void toggleFeeding() {
  feedingActive = !feedingActive;
  time_t now;
  time(&now);

  xSemaphoreTake(stateMutex, portMAX_DELAY);
  if (feedingActive) recordFeedStart();
  else               recordFeedStop();
  xSemaphoreGive(stateMutex);

  if (gatewayMode()) {
    enqueuePendingEvent(feedingActive ? "start" : "stop", now);
  }

  setCounter(feedingActive ? "Feeding now" : "Last fed",
             feedingActive ? "开始喂养"      : "结束喂养",
             0);
}

// ---- View tickers ---------------------------------------------------------

void updateCounter() {
  if (currentView != VIEW_COUNTER || !activeCounter.active) return;
  if (millis() - lastCounterDrawMs < 500) return;
  lastCounterDrawMs = millis();
  uint32_t elapsed = activeCounter.baseElapsedSeconds +
                     ((millis() - activeCounter.startedAtMs) / 1000);
  drawCounter(elapsed);
}

void updateClockScreen() {
  if (currentView != VIEW_CLOCK) return;
  if (millis() - lastClockDrawMs < 500) return;
  lastClockDrawMs = millis();
  drawClockScreen();
}

// ---- NTP ------------------------------------------------------------------

const char* const NTP_CN_SERVERS[] = {
  "cn.ntp.org.cn", "ntp.ntsc.ac.cn", "cn.pool.ntp.org",
};
const char* const NTP_INTL_SERVERS[] = {
  "pool.ntp.org", "time.cloudflare.com", "time.google.com",
};
constexpr uint32_t NTP_PER_SERVER_TIMEOUT_MS = 6000;

bool tryNtpServer(const char* host, uint32_t timeoutMs) {
  configTime(NTP_GMT_OFFSET_SEC, NTP_DST_OFFSET_SEC, host);
  struct tm timeinfo;
  return getLocalTime(&timeinfo, timeoutMs);
}

bool tryNtpServerList(const char* const* servers, size_t count, const char* groupLabel) {
  for (size_t i = 0; i < count; i++) {
    drawStatus("Syncing time", String(groupLabel) + ": " + servers[i]);
    Serial.printf("NTP try %s\n", servers[i]);
    if (tryNtpServer(servers[i], NTP_PER_SERVER_TIMEOUT_MS)) {
      Serial.printf("NTP ok via %s\n", servers[i]);
      return true;
    }
    Serial.printf("NTP fail %s\n", servers[i]);
  }
  return false;
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  drawStatus("WiFi", "Connecting...");
  uint32_t started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < 20000) delay(250);
  if (WiFi.status() != WL_CONNECTED) {
    drawStatus("WiFi failed", "Check config.h");
    return;
  }

  drawStatus("WiFi", "Waiting for DHCP...");
  uint32_t dhcpStarted = millis();
  while (WiFi.localIP() == IPAddress(0, 0, 0, 0) && millis() - dhcpStarted < 10000) {
    delay(100);
  }
  if (WiFi.localIP() == IPAddress(0, 0, 0, 0)) {
    drawStatus("DHCP failed", "No IP from router");
    return;
  }
  Serial.printf("DHCP ok, IP=%s\n", WiFi.localIP().toString().c_str());

  if (!tryNtpServerList(NTP_CN_SERVERS,
                        sizeof(NTP_CN_SERVERS) / sizeof(NTP_CN_SERVERS[0]),
                        "CN")) {
    tryNtpServerList(NTP_INTL_SERVERS,
                     sizeof(NTP_INTL_SERVERS) / sizeof(NTP_INTL_SERVERS[0]),
                     "global");
  }
  drawClockScreen();
}

}  // namespace

// ---------------------------------------------------------------------------
// Time + string helpers (declared in state.h; views.cpp links against these)
// ---------------------------------------------------------------------------

String currentTimestamp() {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo, 0)) return String("(time not synced)");
  char buf[32];
  strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M", &timeinfo);
  return String(buf);
}

String formatElapsed(uint32_t seconds) {
  uint32_t hours   = seconds / 3600;
  uint32_t minutes = (seconds % 3600) / 60;
  char buffer[8];
  snprintf(buffer, sizeof(buffer), "%02lu:%02lu",
           (unsigned long)hours, (unsigned long)minutes);
  return String(buffer);
}

bool getClockText(String& out) {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo, 0)) return false;
  if (timeinfo.tm_year < (2024 - 1900)) return false;
  char buf[8];
  snprintf(buf, sizeof(buf), "%02d:%02d", timeinfo.tm_hour, timeinfo.tm_min);
  out = String(buf);
  return true;
}

bool getDateText(String& out) {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo, 0)) return false;
  if (timeinfo.tm_year < (2024 - 1900)) return false;
  char buf[16];
  snprintf(buf, sizeof(buf), "%04d-%02d-%02d",
           timeinfo.tm_year + 1900, timeinfo.tm_mon + 1, timeinfo.tm_mday);
  out = String(buf);
  return true;
}

// ---------------------------------------------------------------------------
// Arduino entry points
// ---------------------------------------------------------------------------

void setup() {
  Serial.begin(115200);
  stateMutex = xSemaphoreCreateMutex();

  hal::Board& board = hal::currentBoard();
  board.init();
  board.backlight(255);

  hal::InputSource& in = board.input();
  in.onPrimaryAction(cycleView);
  in.onSecondaryAction(toggleFeeding);

  connectWiFi();

  if (gatewayMode()) {
    Serial.printf("Gateway mode -> %s (device_id=%s)\n", GATEWAY_URL, DEVICE_ID);
    // 16K stack — TLS handshakes can need >8K when GATEWAY_URL is https.
    xTaskCreatePinnedToCore(gatewayTask, "gateway", 16384, nullptr, 1, nullptr, 0);
  } else {
    Serial.println("Standalone mode (no gateway)");
  }
}

void loop() {
  if (gatewayStateDirty) {
    gatewayStateDirty = false;
    redrawCurrentView();
  }
  updateCounter();
  updateClockScreen();
  hal::currentBoard().input().poll();
  delay(5);
}
