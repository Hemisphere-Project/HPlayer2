# radar_ld2450 — HPlayer2 proximity radar (LD2450 + ESP32)

Successor of [`../Atom-prox`](../Atom-prox) (a PIR that failed in direct sun). An
**HLK-LD2450** 24 GHz radar on UART, an ESP32 bridge, and a USB cable to the host
RPi. Dispositif C of Biennale 2026: proximity triggers an outdoor audio player.
Production target is an **ESP32-C3 mini** (`env:c3`); an **M5 Atom Matrix**
(`env:atom`) serves as desk-test rig with a spatial LED display.

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

| LD2450 | ESP32-C3 (`env:c3`) | Atom Matrix (`env:atom`, Grove) |
|--------|---------------------|--------------------------------|
| TX     | GPIO20 (`RADAR_RX`) — the only data wire needed | G32 |
| RX     | GPIO21 (`RADAR_TX`) — unused unless you configure the sensor | G26 |
| 5V / GND | 5V / GND | 5V / GND |

USB from the ESP32 to the host RPi. On the C3, the onboard LED (GPIO8, active-low)
lights while at least one target is present — a local sanity light, not a decision.
On the Atom, the 5×5 matrix plots each target on a 4 m × ±2 m grid (radar at the top
edge, one color per LD2450 slot); a dim red center dot means frames flow but the
zone is empty. Debug display only — the wire format is identical on both envs.

## Build / flash (PlatformIO)

```
pio run -e c3 -t upload       # production (ESP32-C3 mini)
pio run -e atom -t upload     # desk-test rig (M5 Atom Matrix)
pio device monitor            # optional; same serial as the data link
```

Set `board =` in `platformio.ini` to your exact C3 variant if `esp32-c3-devkitm-1`
doesn't match (all C3s share the chip; pins are set via `-DRADAR_RX/-DRADAR_TX`).

## USB mode

Built with **HW USB-Serial/JTAG CDC** (`-DARDUINO_USB_MODE=1`): the port survives
firmware crashes and flashing needs no button dance. It enumerates as Espressif
`303a:1001` — the same VID:PID as the CoreS3 teleco2 remote. The 6 outdoor players
carry no remote, so there's no collision. If a player ever needs both, give one a
distinct USB product string via a TinyUSB build env and tighten the host filters.

The Atom rig instead enumerates through its CH9102 converter ("M5 Serial Converter",
`1a86:55d4`) — NOT matched by the host interface's default filter (on purpose: it
stays production-shaped). To point a player at the test rig, pass a filter:
`hplayer.addInterface('radar', "M5 Serial|1a86:55d4")`.

## LD2450 mode

Assumes the sensor's factory **multi-target** streaming mode (the default). If a unit
ships in single-target mode, set it once with the vendor tool — not from here, to keep
the firmware dumb.

The board's external **2.4 GHz antenna is Bluetooth only** (BLE config via the
HLKRadarTool phone app) — the 24 GHz radar uses the on-PCB patch antennas next to
the chip. Unused by this UART-only setup: the module streams fine with the antenna
unplugged, and BLE can be disabled for good with the vendor tool if a sealed box
shouldn't advertise itself.
