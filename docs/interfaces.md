# HPlayer2 — Interface Reference

> **Status: first draft.** HPlayer2 has almost no docstrings, so this reference was reconstructed by
> reading the source (`core/interfaces/`). Constructor signatures and event names are accurate as of
> 2026-06-25; behavioral notes and robustness caveats come from the codebase audit (see
> [`ROADMAP.md`](../ROADMAP.md), Phases 2 & 4). Please correct anything that drifts from the code.

Interfaces are HPlayer2's **I/O modules** — the bridge between the media engine and the outside world
(networks, controllers, sensors, screens). They are *optional* and *pluggable*: a profile enables only
the ones it needs.

---

## Contents

- [How interfaces work](#how-interfaces-work)
  - [Adding an interface](#adding-an-interface)
  - [Graceful degradation](#graceful-degradation)
  - [The event model (patching)](#the-event-model-patching)
- [Quick reference](#quick-reference)
- [Network & protocol](#network--protocol): [osc](#osc) · [http](#http) · [http2](#http2) · [mqtt](#mqtt) · [zyre](#zyre) · [regie](#regie)
- [MIDI & timecode](#midi--timecode): [midictrl](#midictrl) · [mtc](#mtc) · [nowde](#nowde)
- [GPIO, sensors & panels](#gpio-sensors--panels): [gpio](#gpio) · [hcon](#hcon) · [keypad](#keypad) · [nfc](#nfc)
- [Input devices](#input-devices): [keyboard](#keyboard)
- [Serial & wireless remotes](#serial--wireless-remotes): [serial](#serial) · [btserial](#btserial) · [teleco](#teleco)
- [Timing](#timing): [ticker](#ticker)
- [Robustness & cross-platform status](#robustness--cross-platform-status)

---

## How interfaces work

### Adding an interface

In a profile you add interfaces to the engine with `addInterface()`:

```python
hplayer.addInterface('osc', 4000, 4001)     # name, then constructor args
```

The loader (`core/engine/hplayer.py:380`, `core/interfaces/__init__.py`) resolves the name like this:

1. imports the module `core/interfaces/<name>.py`,
2. instantiates the class `<Name>Interface` (the name `.title()`-cased + `"Interface"`, e.g.
   `osc → OscInterface`, `http2 → Http2Interface`, `midictrl → MidictrlInterface`),
3. calls it as `InterfaceClass(hplayer, *args)` — so **every argument after the name is passed
   straight to the constructor**.

Retrieve a live instance later with `hplayer.interface('osc')`.

### Graceful degradation

Each interface declares its dependencies and **fails soft**: if a required Python library or piece of
hardware is missing, the constructor raises `RuntimeError`, and `addInterface()` catches it, logs a
line, and returns `None` instead of crashing the program:

```
[hplayer]  interface gpio not available: No module named 'RPi'
[hplayer]  interface nfc disabled: PN532 not found
```

This is what lets the **same profile** run on a Raspberry Pi (with GPIO/NFC) and on an N100 or a
desktop (where those interfaces simply stay disabled). *Caveat:* coverage is uneven today — see
[Robustness & cross-platform status](#robustness--cross-platform-status).

### The event model (patching)

Interfaces communicate with the engine over the event bus (`pymitter`). An interface emits a short
event name; the engine re-broadcasts it **prefixed with the interface name** (lower-cased). So an
event `E` emitted by the `keyboard` interface arrives at the engine as `keyboard.E`.

Patch it in a profile with the `@hplayer.on(...)` decorator:

```python
@hplayer.on('keyboard.KEY_KPPLUS-down')     # '<interface>.<event>'
@hplayer.on('keyboard.KEY_KPPLUS-hold')
def volup(ev, *args):
    hplayer.emit('volinc', 1)               # emit an engine command back
```

The handler signature is always `(ev, *args)` where `ev` is the triggering event string and `*args`
are the values the interface attached. Wildcards work too: `@hplayer.on('osc.*')`.

---

## Quick reference

| Interface | Medium | Dir | Requires (lib / hardware) | Platforms |
|-----------|--------|-----|---------------------------|-----------|
| [osc](#osc) | OSC / UDP | in (+out) | `python-osc` | all |
| [http](#http) | HTTP REST | in/out | stdlib | all |
| [http2](#http2) | HTTP + WebSocket (Web UI) | in/out | `flask-socketio`, `pillow` | all |
| [mqtt](#mqtt) | MQTT pub/sub | in/out | `paho-mqtt` + broker | all |
| [zyre](#zyre) | ZeroMQ / Zyre P2P | in/out | `zyre`, `czmq` | Linux/macOS |
| [regie](#regie) | HTTP + WebSocket (multi-peer UI) | in/out | `flask-socketio`, `watchdog` | all |
| [midictrl](#midictrl) | MIDI control surface | in | `python-rtmidi` | Linux/macOS/Win |
| [mtc](#mtc) | MIDI Time Code | in | `mido`, `timecode` | Linux/macOS/Win |
| [nowde](#nowde) | MIDI Time Code (continuous sync) | in | `mido`, `timecode` | Linux/macOS/Win |
| [gpio](#gpio) | GPIO digital I/O | in/out | `RPi.GPIO` / `rpi-lgpio` | **Pi only** |
| [hcon](#hcon) | GPIO (preset pin map) | in/out | `RPi.GPIO` | **Pi only** |
| [keypad](#keypad) | I²C LCD + buttons | in/out | `Adafruit_CharLCD` | **Pi + I²C** |
| [nfc](#nfc) | NFC / RFID reader | in | `Adafruit_PN532` + PN532 | **Pi only** |
| [keyboard](#keyboard) | USB keyboard / numpad / IR | in | `evdev` | **Linux** |
| [serial](#serial) | UART / serial | in | `pyserial` | all |
| [btserial](#btserial) | Bluetooth RFCOMM | in/out | `pybluez` + adapter | all (BT) |
| [teleco](#teleco) | Serial remote (Arduino) | in/out | `pyserial` + device | all |
| [ticker](#ticker) | Internal metronome | out | stdlib | all |

`Dir` = direction relative to the player (in = control input, out = output/feedback).

---

## Network & protocol

### osc

Receive (and optionally send) Open Sound Control over UDP — e.g. from TouchOSC, Max/MSP, a lighting desk.

- **Add:** `addInterface('osc', in_port, out_port=0, hostOut=None)`
- **Params:** `in_port` — UDP port to listen on; `out_port` — port to send replies (0 = disabled);
  `hostOut` — destination host for outgoing OSC.
- **Requires:** `python-osc` (optional `zeroconf` for service advertising).
- **Emits:** the **incoming OSC address with its leading `/` stripped**, carrying the OSC arguments.
  e.g. an incoming `/play 1` → event `osc.play` with arg `1`. (`osc.py:117`)
- **Example:**
  ```python
  hplayer.addInterface('osc', 4000, 4001)
  @hplayer.on('osc.play')
  def _(ev, *a): hplayer.emit('play', *a)
  ```

### http

A minimal HTTP REST endpoint for simple network control/automation.

- **Add:** `addInterface('http', port)`
- **Requires:** Python stdlib only (optional `zeroconf`).
- **Notes:** lightweight command API. For an interactive UI use [http2](#http2) instead. Has no
  request timeout and blocks until shutdown (`http.py:22`).

### http2

The responsive **web UI** (control page + media browser + file upload) over Flask + Socket.IO.

- **Add:** `addInterface('http2', port, confe={})`
- **Params:** `port` — HTTP port; `confe` — a dict of UI options. Observed keys in profiles:
  `playlist`, `loop`, `mute` (show/hide those controls) and `page` (`'mini'`/`'simple'`/`'full'`,
  selects the template). e.g. `addInterface('http2', 80, {'page': 'mini'})`.
- **Requires:** `flask`, `flask-socketio`, `werkzeug`; `pillow` (optional, image thumbnailing).
- **Emits (internal, to its socket clients):** `status`, `settings.updated`, `playlist.updated`,
  `files`, `file-uploaded`, `config`, `hardreset`. Most profiles don't patch these — http2 is
  largely self-contained.
- **Caveats:** no server-side upload size limit; `stop()` is currently a no-op (see ROADMAP B3/B8/I5).
- **Example:** `hplayer.addInterface('http2', 8080)`

### mqtt

Bridge to an MQTT broker for pub/sub control (e.g. ESP remotes, home-automation, multi-device cues).

- **Add:** `addInterface('mqtt', broker)`
- **Params:** `broker` — broker host/IP (e.g. `'10.0.0.1'`).
- **Requires:** `paho-mqtt` and a reachable broker.
- **Emits:** an event derived from the topic — the topic is split on `/`, the first two segments are
  dropped, and the rest are joined with `.`; the payload is split on `§` into args. (`mqtt.py:53-54`)
- **Caveats:** the connect loop blocks; disconnect can hang if the broker vanishes (ROADMAP I7).

### zyre

Peer-to-peer discovery and **synchronized triggers** over ZeroMQ/Zyre — the backbone of multi-device
shows. Auto-discovers other HPlayer2 nodes on the LAN and exchanges timestamped events + status.

- **Add:** `addInterface('zyre', netiface=None)`
- **Params:** `netiface` — the network interface to bind discovery to (e.g. `'wlan0'`, `'eth0'`,
  `'wlan1'`). If omitted, Zyre picks one.
- **Requires:** `zyre` + `czmq` (vendored under `scripts/`; Linux/macOS).
- **Emits:** `zyre.event` (a received peer trigger), `zyre.peer.link`, `zyre.planned`. It also
  publishes this node's player status to peers automatically.
- **Caveats:** shutdown is fragile (`stop()` is commented out — "HANGS!", `zyre.py:602`); there is an
  unmodeled gap between a synced trigger and the actual frame/audio. Both are central to ROADMAP
  Phase 3 (sync convergence).
- **Example:** `hplayer.addInterface('zyre', 'eth0')`

### regie

A **multi-peer control surface**: a web UI (Flask + Socket.IO) that drives sequences across peers and
watches a project file on disk for live edits. The seed of the future central dashboard (ROADMAP Phase 6).

- **Add:** `addInterface('regie', port, datapath, latency=437)`
- **Params:** `port` — HTTP port; `datapath` — folder holding the project (watched for changes);
  `latency` — scheduling/sync latency in ms.
- **Requires:** `flask-socketio`, `watchdog`.
- **Emits:** `regie.peers.triggers`, `regie.peers.subscribe`, `regie.peers.getlink`,
  `regie.playingseq`.
- **Example:** `hplayer.addInterface('regie', 9111, projectfolder)`

---

## MIDI & timecode

### midictrl

Map a **MIDI control surface** (pads, knobs, faders — e.g. an Akai LPD8) to player actions.

- **Add:** `addInterface('midictrl', device_filter="LPD8", retry=0)`
- **Params:** `device_filter` — substring/name of the MIDI input port to match; `retry` — connection
  retry attempts (with exponential backoff).
- **Requires:** `python-rtmidi`.
- **Emits** one event per MIDI message, named by a short type, carrying a dict payload
  (`midictrl.py:64-96`):
  - `midictrl.noteon` — `{channel, note, velocity}`
  - `midictrl.noteoff` — `{channel, note, velocity}`
  - `midictrl.cc` (control change) — `{channel, control, value}`
  - `midictrl.pc` (program change) — `{channel, program}`
  - `midictrl.ready` — emitted on successful connect.
- **Notes:** has the most robust reconnection logic of all interfaces — a good template for others.
- **Example:**
  ```python
  hplayer.addInterface('midictrl', 'LPD8', 10)
  @hplayer.on('midictrl.noteon')
  def _(ev, msg): hplayer.emit('play', msg['note'])
  ```

### mtc

Receive raw **MIDI Time Code** (SMPTE over MIDI). A thin receiver — emits timecode frames; the sync
logic lives in a handler or in [nowde](#nowde).

- **Add:** `addInterface('mtc', port_name, max_retry=0)`
- **Params:** `port_name` — MIDI input port; accepts a **string or a compiled regex** (profiles use
  `re.compile(...)` to match e.g. an rtpMIDI port); `max_retry` — connection retries.
- **Requires:** `mido`, `timecode`.
- **Emits:** `mtc.qf` (quarter-frame, 8 per frame) and `mtc.ff` (full-frame / sysex).

### nowde

The **continuous-sync MTC engine**: like `mtc`, but it directly drives a player to stay frame-locked
to incoming timecode — adaptive speed correction, dead-zone hysteresis, smoothing, kickstart. Use this
when you want a player slaved to an external timecode clock.

- **Add:** `addInterface('nowde', player=None, port_name=None, max_retry=0)`
- **Params:** `player` — the player to slave (defaults to the first player if omitted);
  `port_name` — MIDI input port (string or regex; defaults to a `^Nowde` match); `max_retry` — retries.
- **Requires:** `mido`, `timecode`.
- **Emits:** `nowde.qf`, `nowde.ff`. Selects media via MIDI CC#100 (filename-pattern match).
- **Example:** `player = hplayer.addPlayer('mpv','p'); hplayer.addInterface('nowde', player)`

---

## GPIO, sensors & panels

### gpio

Read buttons/switches and drive outputs on the Raspberry Pi GPIO header.

- **Add:** `addInterface('gpio', pins_watch=[], debounce=200, antispike=100, pullupdown='PUP')`
- **Params:** `pins_watch` — list of BCM pin numbers to watch; `debounce` — ms debounce window;
  `antispike` — ms anti-spike filter; `pullupdown` — `'PUP'` (pull-up) or `'PDN'` (pull-down).
- **Requires:** `RPi.GPIO` / `rpi-lgpio` — **Raspberry Pi only** (disabled elsewhere).
- **Emits per pin** (where `<pin>` is the pin number): `gpio.<pin>` with `1`/`0`, plus
  `gpio.<pin>-on` and `gpio.<pin>-off`. (`gpio.py:37-44`)
- **Example:**
  ```python
  hplayer.addInterface('gpio', [21,20,16,26], 310)
  @hplayer.on('gpio.21-on')
  def _(ev, *a): hplayer.emit('play', 0)
  ```

### hcon

A convenience GPIO profile with a fixed pin mapping (the "Hemisphere connector"). Subclasses `gpio`.

- **Add:** `addInterface('hcon', pins_watch=[], debounce=50)`
- **Requires / platform:** same as [gpio](#gpio) — **Pi only**.

### keypad

Adafruit character-LCD + button shield (16×2 LCD with directional buttons) over I²C.

- **Add:** `addInterface('keypad')`
- **Requires:** `Adafruit_CharLCD` + the I²C LCD shield. Falls back to a **MockLCD** (logs instead of
  displaying) when the hardware isn't present, so it degrades on non-Pi hosts. (`keypad.py:88-120`)
- **Emits** per button: `keypad.<btn>`, `keypad.<btn>-hold`, `keypad.<btn>-release`. (`keypad.py:192-200`)

### nfc

Read NFC/RFID tags from a PN532 reader (I²C/SPI) — e.g. tap-a-card to trigger media.

- **Add:** `addInterface('nfc', timeout=1000, divider=5)`
- **Params:** `timeout` — read timeout (ms); `divider` — polling divider (read cadence).
- **Requires:** `Adafruit_PN532` + a PN532 module — **Pi only**.
- **Emits:** `nfc.card` (with the tag UID) when a tag is present, `nfc.nocard` when removed.
- **Caveats:** hard-fails if the reader isn't found at startup; no hot-plug (ROADMAP I8).

---

## Input devices

### keyboard

USB keyboard, numeric keypad, or **IR remote** presented as a keyboard (via `evdev`). Hot-plug aware.

- **Add:** `addInterface('keyboard')`
- **Requires:** `evdev` — **Linux only** (uses `/dev/input`).
- **Emits:** `keyboard.<KEYCODE>-<mode>`, where `<KEYCODE>` is an evdev key name and `<mode>` is
  `down` / `hold` / `up` — e.g. `keyboard.KEY_KPPLUS-down`, `keyboard.KEY_ENTER-hold`. (`keyboard.py:126`)
- **Example:** see [The event model](#the-event-model-patching) above.

---

## Serial & wireless remotes

### serial

Generic line-based serial/UART input — wired sensors, microcontrollers, custom remotes.

- **Add:** `addInterface('serial', filter="", maxRetry=0)`
- **Params:** `filter` — port-name pattern to select the device (profiles use patterns like `'^M5'`,
  `'^CP2102'`); `maxRetry` — retries while searching for the port.
- **Requires:** `pyserial`.
- **Emits:** `serial.connected` / `serial.disconnected` on link state; incoming messages are forwarded
  as events.
- **Caveats:** no reconnect after an error mid-session (ROADMAP I6).
- **Example:** `hplayer.addInterface('serial', '^M5', 10)`

### btserial

Bluetooth RFCOMM serial — e.g. a wireless ESP/M5 remote paired over Bluetooth.

- **Add:** `addInterface('btserial', device)`
- **Params:** `device` — the Bluetooth device name/address to connect to.
- **Requires:** `pybluez` + a Bluetooth adapter.
- **Notes:** scans + retries to find the device with backoff.

### teleco

A purpose-built **serial remote control surface** (Arduino Pro Micro / Leonardo) with an LCD: a full
transport remote rather than a raw data link.

- **Add:** `addInterface('teleco')`
- **Requires:** `pyserial` + the Teleco device.
- **Emits** transport commands ready to patch to player actions: `teleco.play`, `teleco.pause`,
  `teleco.stop`, `teleco.resume`, `teleco.next`, `teleco.prev`, `teleco.skip`, `teleco.loop`,
  `teleco.fade`, `teleco.unfade`, `teleco.volume`, `teleco.hardreset`, `teleco.ready`.

---

## Timing

### ticker

An internal metronome that emits an event at a fixed tempo — handy for scheduled/rhythmic triggers.

- **Add:** `addInterface('ticker', bpm, event='tick')`
- **Params:** `bpm` — beats per minute; `event` — the event name to emit (default `'tick'`).
- **Emits:** `ticker.<event>` with an incrementing counter, every beat. (`ticker.py:18`)
- **Caveat:** simple sleep loop, no drift compensation.
- **Example:** `hplayer.addInterface('ticker', 120, 'tick')`

---

## Robustness & cross-platform status

Breadth is a strength; **uniformity is not** — each interface was hardened ad hoc, so error handling,
reconnection, and shutdown behavior vary. Known recurring gaps (tracked in
[`ROADMAP.md`](../ROADMAP.md) §5.5 and Phase 4):

- **No standard reconnection / hot-plug.** `midictrl` and `keyboard` recover well; `serial`,
  `teleco`, `nfc`, `mqtt` can get stuck after a device disappears.
- **`listen()` loops without error traps** can silently die on an unexpected exception.
- **Inconsistent shutdown** — some interfaces leak threads/sockets on quit (notably `zyre` and
  `http2`).
- **No runtime capability/health query** — a profile can't yet ask "is this interface actually
  connected?".

When writing a profile, assume an interface *may* be unavailable (it returns `None` from
`addInterface`) and *may* drop mid-show. Phases 2 & 4 of the roadmap make the framework enforce a
uniform lifecycle, reconnection, and health-reporting contract so these caveats go away.

---

*This is a living document. As the interface framework lands (ROADMAP Phase 2), each interface will
declare its own params/events/dependencies in code, and this page should be regenerated from that.*
