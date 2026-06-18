# babytime

Baby-feeding tracker for the Alientek DNESP32S3B board. An optional Docker
gateway lets multiple units share a durable activity log, edited from a web
UI or driven by a remote agent over a JSON API.

See [ARCHITECTURE.md](ARCHITECTURE.md) for design rationale and
[gateway/README.md](gateway/README.md) for the gateway API and config keys.

## Modes

Pick one in `firmware/include/config.local.h`:

- **Standalone** — `GATEWAY_URL` empty. Device owns an in-RAM ring of the
  last 8 feedings, no networking except NTP. Cleared on reboot.
- **Gateway** — `GATEWAY_URL` set to your Docker host (e.g.
  `http://192.168.1.1:8080`). Events go to the gateway, which keeps a
  durable SQLite log, hosts the web UI, and exposes a JSON API a remote
  agent can read and write. Multiple ESP32s can share one gateway.

## Hardware

Alientek DNESP32S3B (ESP32-S3R8, 16 MB flash, 8 MB OPI PSRAM):

- LCD: ST7789V via parallel 8080 8-bit (LCD_CAM peripheral), 320×240
- IO expander: XL9555 (PCA9555-compatible) at I²C 0x20 (SDA = GPIO 48, SCL = GPIO 45)
- Backlight enable: XL9555 P0.7
- K2 / BOOT: GPIO 0
- K1: XL9555 P0.4

## Firmware setup

1. Install PlatformIO (`sudo pacman -S platformio-core platformio-core-udev` on Arch).
2. `cp firmware/include/config.local.example.h firmware/include/config.local.h` and edit Wi-Fi + (optional) gateway settings.
3. `make flash` (auto-detects port; override with `PORT=/dev/ttyACM0`).

Minimum `config.local.h`:

```cpp
#define WIFI_SSID "your-wifi-name"
#define WIFI_PASSWORD "your-wifi-password"

// Standalone: leave GATEWAY_URL empty.
// Gateway: http:// or https:// (TLS uses setInsecure() unless you pin a CA).
#define GATEWAY_URL "http://192.168.1.1:8080"
#define GATEWAY_TOKEN ""        // matches gateway env, if set
#define DEVICE_ID "bedroom"     // identifies this unit in records

#define NTP_GMT_OFFSET_SEC 8*3600   // your timezone in seconds
```

## Gateway setup

```sh
cd gateway
docker compose up -d --build
```

Open <http://localhost:8080/>. One page: records table with inline edit, an
Add-record form, per-date day-note fields, and the configuration form. Set
`feeding_alert_minutes` there to blink the top activity buttons and device
display after the last feeding is that many minutes old (`120` by default).
Set
`GATEWAY_TOKEN` in `docker-compose.yml` to require the token on every route
(Bearer for machines, HTTP Basic password for browsers); clients in
`trusted_networks` (default `10.0.0.0/8`) skip auth. Leave the token empty to
trust everyone.

## Buttons

- **K2** — toggle feeding (start ↔ stop). Display flips to the counter view.
- **K1** — cycle Clock → History → Counter views.

When idle and a completed feeding exists, the firmware alternates the Clock
and Last fed counter views every 5 seconds. An active feeding stays on the live
counter view.

GPIO 0 is the chip's BOOT strap pin; holding it during reset puts the chip
into download mode for flashing.

## Make targets

- `make flash` — build + upload firmware
- `make flash PORT=/dev/ttyACM0` — build + upload firmware via specific port
- `make monitor` — open serial monitor (opening the port may toggle DTR/RTS and reset the chip)
- `make flash-monitor` — flash, then monitor
- `make build` / `make clean`
