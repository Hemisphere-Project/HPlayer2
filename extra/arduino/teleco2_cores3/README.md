# TELECO2 — HPlayer2 USB remote (M5Stack CoreS3)

Touchscreen remote that plugs over USB-C into any HPlayer2 player.
Speaks **protocol v1** — authoritative spec in `core/interfaces/teleco2.py` (host side).

- **Status bar**: scrolling current-media title, peer count, wifi rssi, volume.
- **3 pages**: transport (PREV / PLAY-PAUSE / STOP / NEXT + volume), media list
  (drag to scroll, tap to play), peers (name + zyre link health, self marked).
- **Screen lock**: double-tap the status bar to lock, double-tap anywhere to unlock.
- **Hotplug**: powered by the player's USB port; shows "waiting for HPlayer2..." until
  the host talks, greys out after 8 s of silence (player rebooting), recovers alone.

## Build / flash (PlatformIO)

```
pio run -e cores3 -t upload        # default env
pio device monitor                 # optional, same CDC as the protocol link
```

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

Pick after the on-player robustness test (replug, service restart, fw crash).
