# TELECO2 — HPlayer2 remote (M5Stack CoreS3)

Touchscreen remote that plugs over USB-C into any HPlayer2 player, or (fw 6) runs on its
battery over WiFi.
Speaks **protocol v1** — authoritative spec in `core/interfaces/teleco2.py` (host side).

- **Status bar**: scrolling current-media title, peer count, wifi rssi, volume.
- **3 pages**: transport (PREV / PLAY-PAUSE / STOP / NEXT + volume), media list
  (drag to scroll, tap to play), peers (name + zyre link health, self marked).
- **Screen lock**: the remote **boots locked**. Tap the [PLAY] tab 5 times fast
  (< 0.6 s between taps) to unlock or re-lock. Locked: only page switching stays
  active, a padlock shows in the status bar, and touching anything else pops a
  "LOCKED" alert with the unlock hint. No dimming — the screen stays readable.
- **Hotplug**: powered by the player's USB port; shows "waiting for HPlayer2..." until
  the host talks, greys out after 8 s of silence (player rebooting), recovers alone.

## Wireless (fw 6, hplayer2#t-090)

- **USB wins**: VBUS plus a player talking on the USB = USB mode, WiFi **off** (fw 5 behaviour:
  no dimming, no automatic re-lock). VBUS without a player (a charger, a laptop) stays wireless
  and charges. One transport is alive at a time.
- **On WiFi**: joins the show's SSID (learned from a player's `net` over USB, `pisync` by default;
  open networks only, a hidden SSID is joined by name). Discovery: UDP `find` to port 3739,
  players answer `here` (name, port, leader, signal). Attach order: the **pinned** player (tap it
  on PEERS; tap again to unpin) → the current one → the last used → the clock leader if its
  signal is ≥ 50 → the best signal. One TCP session (port 3740, protocol v1 lines, `hb` every
  1 s); no host line for 3 s = dead: buttons disabled, never queued, probe and attach again.
  Never a byte on the wallclock's 3738.
- **Status bar**: battery % (amber ≤ 15, red ≤ 5, a bolt while charging), the player's name, the
  transport (USB / WiFi arcs) with its signal, SYNC. States: NO WIFI → SEARCHING → LINKING.
- **Power** (on WiFi): dims after 20 s idle — the waking touch only wakes —, re-locks after 2 min
  idle; 10 min without WiFi on battery: a one-minute countdown (a touch postpones it), then the
  screen says so and the AXP2101 powers off (power button to restart). Speaker, mic, IMU and the
  5 V output stay off; CPU 160 MHz; WiFi modem sleep. `bat <pct> <chg>` goes to the player every
  30 s (its log). Bench build with a 1-minute power-off: `PLATFORMIO_BUILD_FLAGS="-DOFF_AFTER_S=60"`.
- **Release**: the v6 image must reach **every** player before any remote runs wireless — a player
  still shipping v5 auto-flashes a v6 remote back to v5 (the host flashes on `!=`).

## Build / flash (PlatformIO)

```
pio run -e cores3 -t upload        # default env
pio device monitor                 # optional, same CDC as the protocol link
```

## Auto-flash from the player

The repo ships a merged flash image `dist/teleco2_cores3-v<N>.bin` (bootloader +
partitions + app, flashable at `0x0`). The firmware announces its version in the
hello beacon (`hello <proto> <fw>`, see `src/version.h`); when the player sees an
off-version remote and `esptool` is installed, it reflashes it on sight over the
ROM USB-Serial/JTAG CDC — buttonless, works whatever state the firmware is in.
Updating a deployed remote, or enrolling a blank spare that already carries any
teleco2 firmware, costs nothing but plugging it into an up-to-date player.

To release a new firmware: bump `FW_VERSION` in `src/version.h`, rebuild, rebuild
the merged image into `dist/` (recipe in `version.h`), commit both.

## Host side

Profile: `hplayer.addInterface('teleco2')` (see `profiles/anna.py`), or
`hplayer.addInterface('teleco2', True)` for standalone (non-parc) players.
Test without a player: `python3 extra/test/teleco2_mockhost.py`.

## USB mode

- **`cores3` (default)** — HW USB-Serial/JTAG CDC: the port survives firmware
  crashes and flashing needs no button dance. Enumerates as Espressif `303a:1001`,
  matched by the host filter `"HPlayer2|303a:1001"`.
- **`cores3-tinyusb`** — TinyUSB OTG with product string "HPlayer2 Remote".
  Cleaner descriptor, but a crashed firmware drops the port: re-flash may need
  manual download mode (hold RST until the LED turns green, check M5 docs).

`cores3` stays the shipped default: player-driven auto-flash of a plugged remote
needs the ROM CDC port, which survives any firmware state and flashes without a
button dance — a crashed tinyusb remote drops off the bus and needs hands on RST.
The tinyusb env is kept maintained as the descriptor-level fallback.

### The `303a:1001` collision

`303a:1001` is not unique to this remote — it is the generic Espressif
USB-Serial/JTAG ID, shared by **any** ESP32-family device in ROM CDC mode
that may sit on the same player (the radar box `../radar_ld2450`, JTAG-mode dev
boards, other project hardware). Host side (`core/interfaces/teleco2.py`):

- under the default filter a port is only the remote's once the device proves
  it: a hello carrying its fw (`hello 1 <fw>`, repeated every 3 s until
  answered), a valid command, or a bare `hello 1` seen **twice** — the radar box
  prints one bare `hello 1` on boot, and a flash must never fire on it;
- a radar frame line, or no hello within 15 s (8 s stale + one 3 s beacon +
  margin), rejects the port: the host re-scans excluding it until it is
  unplugged. One tty is never opened by two interfaces of the same player;
- the per-player `teleco2-filter` setting is the manual escape hatch — key it
  on the USB **serial string** (`SER=<chip MAC>`), never on VID:PID. A filter
  set there (or passed by the profile) is trusted: no probing, and a silent
  device still gets the state dump after 10 s, as before;
- all of this is the USB link's: a TCP session (WiFi) answered the player's
  `here`, so it is never probed and no radar box can sit behind it.
