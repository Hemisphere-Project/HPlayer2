# TELECO2 — HPlayer2 USB remote (M5Stack CoreS3)

Touchscreen remote that plugs over USB-C into any HPlayer2 player.
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
USB-Serial/JTAG ID, shared by **any** ESP32-S3-family device in ROM CDC mode
that may sit on the same player (JTAG-mode dev boards, other project hardware).
Two consequences on the host side:

- protocol v1 is self-identifying: the remote repeats `hello 1` every 3 s until
  answered, so the host can drop a port that yields no valid protocol line
  within ~10 s and rescan excluding it;
- the per-player `teleco2-filter` setting remains the manual escape hatch —
  key it on the USB **serial string** (`SER=<chip MAC>`), never on VID:PID.
