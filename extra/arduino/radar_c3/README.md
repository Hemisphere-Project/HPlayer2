# radar_c3 — HPlayer2 proximity radar (ESP32-C3 + LD2450)

Successor of [`../Atom-prox`](../Atom-prox) (a PIR that failed in direct sun). An
**HLK-LD2450** 24 GHz radar on UART, an **ESP32-C3 mini**, and a USB-C cable to the
host RPi. Dispositif C of Biennale 2026: proximity triggers an outdoor audio player.

**Deliberately dumb** — no range, no threshold, no hysteresis on the MCU (nobody
reflashes sealed IP55 boxes on site). It decodes LD2450 target frames and forwards
them raw. **Every decision lives on the Pi**, in the host `radar` interface
(`core/interfaces/radar.py`), tunable and exposed on the http2 web UI.

## Wire format (device → host, USB CDC, 115200, LF-terminated)

One line per LD2450 frame:

```
T <x1>,<y1>,<v1> <x2>,<y2>,<v2> ...     # only active targets; a bare "T" = zone empty
```

`x`,`y` in **mm** (`x` lateral, signed; `y` distance, forward-positive), `v` speed in
**cm/s**. On boot the firmware also prints `hello 1` (protocol version); the host
ignores any line it doesn't recognise.

## Wiring

| LD2450 | ESP32-C3 |
|--------|----------|
| TX     | GPIO20 (`RADAR_RX`) — the only data wire needed |
| RX     | GPIO21 (`RADAR_TX`) — unused unless you configure the sensor |
| 5V / GND | 5V / GND |

USB-C from the C3 to the host RPi. The onboard LED (GPIO8, active-low) lights while
at least one target is present — a local sanity light, not a decision.

## Build / flash (PlatformIO)

```
pio run -e c3 -t upload
pio device monitor            # optional; same CDC as the data link
```

Set `board =` in `platformio.ini` to your exact C3 variant if `esp32-c3-devkitm-1`
doesn't match (all C3s share the chip; pins are set via `-DRADAR_RX/-DRADAR_TX`).

## USB mode

Built with **HW USB-Serial/JTAG CDC** (`-DARDUINO_USB_MODE=1`): the port survives
firmware crashes and flashing needs no button dance. It enumerates as Espressif
`303a:1001` — the same VID:PID as the CoreS3 teleco2 remote. The 6 outdoor players
carry no remote, so there's no collision. If a player ever needs both, give one a
distinct USB product string via a TinyUSB build env and tighten the host filters.

## LD2450 mode

Assumes the sensor's factory **multi-target** streaming mode (the default). If a unit
ships in single-target mode, set it once with the vendor tool — not from here, to keep
the firmware dumb.
