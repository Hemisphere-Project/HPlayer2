# HPlayer2 — Writing a Profile

> **Status: first draft.** Reconstructed from the engine source and the example profiles (the code
> has almost no docstrings). Accurate as of 2026-06-25. Command argument signatures are not yet
> formally documented in code — when in doubt, check the handlers in `core/engine/hplayer.py` or copy
> a working example. See [`architecture.md`](architecture.md) for the system overview and
> [`ROADMAP.md`](../ROADMAP.md) for where this is heading.

A **profile** is a small Python file in `profiles/` that *composes* an HPlayer2 instance for one use
case: it creates a player, enables the interfaces you need, patches inputs to actions, and runs. The
profile **is** the program — running `./hplayer2 myshow` simply imports `profiles/myshow.py`.

This is the surface you'll spend most of your time in. The goal of this guide is to make you
productive in an afternoon.

---

## Contents

- [Run a profile](#run-a-profile)
- [Anatomy of a profile](#anatomy-of-a-profile)
- [1 · Create the engine](#1--create-the-engine)
- [2 · Add a player](#2--add-a-player)
- [3 · Add interfaces](#3--add-interfaces)
- [4 · Patch events to actions](#4--patch-events-to-actions)
- [5 · Run](#5--run)
- [Lifecycle hooks (important)](#lifecycle-hooks-important)
- [Controlling playback](#controlling-playback)
- [Worked examples](#worked-examples)
- [Reference appendix](#reference-appendix)
- [Tips & gotchas](#tips--gotchas)

---

## Run a profile

```bash
./hplayer2 myshow        # runs profiles/myshow.py
./hplayer2               # no name → falls back to the 'looper' profile (see launcher.py)
```

To create your own, copy an existing profile to `profiles/myshow.py` and edit it. The best starting
points are [`profiles/looper.py`](../profiles/looper.py) (a minimal USB auto-loop) and
[`profiles/default.py`](../profiles/default.py) (keyboard + OSC + web UI).

---

## Anatomy of a profile

Every profile follows the same five steps:

```python
from core.engine.hplayer import HPlayer2

# 1 — create the engine (where media lives, where settings are saved)
hplayer = HPlayer2(mediaPath='/data/usb', config='/data/myshow.cfg')

# 2 — add a player (the media backend)
player = hplayer.addPlayer('mpv', 'player')

# 3 — add interfaces (the I/O you need)
hplayer.addInterface('keyboard')
hplayer.addInterface('http2', 8080)

# 4 — patch events to actions
@hplayer.on('keyboard.KEY_SPACE-down')
def _(ev, *args):
    hplayer.emit('playpause')

# 5 — run (starts everything; blocks until shutdown)
hplayer.run()
```

---

## 1 · Create the engine

```python
hplayer = HPlayer2(mediaPath='/data/usb', config='/data/myshow.cfg')
```

- **`mediaPath`** — the directory (or list of directories) HPlayer2 scans for media.
- **`config`** — path to a JSON settings file. Persisted settings (volume, loop, …) survive restarts;
  omit it for an ephemeral session.
- **`extraMediaPath`**, **`datadir`** — optional extra search path and data directory. `datadir`
  defaults to a cross-platform location (`platformdirs`), so you don't *have* to use `/data` on a
  desktop or N100.

> The older positional form `HPlayer2('/data/usb', '/data/myshow.cfg')` still works via a
> backward-compat shim, which is why you'll see it in some example profiles. Prefer the keyword form.

Useful engine attributes/helpers you'll reach for:

| Access | What it is |
|--------|-----------|
| `hplayer.settings` | the persistent settings store (`.get(key)`, `.set(key, value)`) |
| `hplayer.playlist` | the media list & cursor (see [Controlling playback](#controlling-playback)) |
| `hplayer.files` | the file manager (`.listFiles('/')` enumerates media) |
| `hplayer.players()` / `hplayer.activePlayer()` | the players / the currently active one |
| `hplayer.interface('osc')` | fetch a live interface instance |
| `hplayer.isRPi()` | `True` on a Raspberry Pi — guard Pi-only interfaces with it |
| `hplayer.log(...)` | log a line through the engine's logger |

---

## 2 · Add a player

```python
player = hplayer.addPlayer('mpv', 'player')   # backend name, instance name
```

`mpv` is the default, fully-supported backend. Others exist (`gst`, `omx`, `jp`, `midi`, `videonet`)
— see [architecture.md](architecture.md#players). You can add **several players**; the engine routes
a `play <file>` to the first player whose file-extension list matches, so e.g. mpv handles video and
`jp` handles audio in the same profile.

`addPlayer` returns the player object (or `None` if that backend isn't available on this host), which
you can keep a reference to for direct calls and for patching its events.

---

## 3 · Add interfaces

```python
hplayer.addInterface('osc', 4000, 4001)
hplayer.addInterface('http2', 8080)
if hplayer.isRPi():
    hplayer.addInterface('gpio', [16, 20, 21], 200, 0, 'PUP')   # only on a Pi
```

Each `addInterface('name', *args)` passes its extra args straight to that interface's constructor. If
the interface's library or hardware is missing, it logs a line and returns `None` — **it won't crash
your profile**, so the same file runs on a Pi, an N100, or a desktop.

👉 Full list of interfaces, their arguments and the events they emit: **[`interfaces.md`](interfaces.md)**.

---

## 4 · Patch events to actions

This is the heart of a profile. Components talk over the **event bus**: an interface emits an event,
the engine re-broadcasts it as `<interface>.<event>`, and you react with the `@…on(...)` decorator.

```python
@hplayer.on('keyboard.KEY_KPPLUS-down')      # an input event…
@hplayer.on('keyboard.KEY_KPPLUS-hold')      # (decorators stack: same handler for several events)
def volup(ev, *args):                        # handler is always (ev, *args)
    hplayer.emit('volinc', 1)                # …emit an engine command
```

- **Listen** with `@hplayer.on('source.event')`. Wildcards work: `@hplayer.on('osc.*')`,
  `@hplayer.on('*.media-end')`.
- You can listen on a specific component too: `@player.on('ready')`,
  `@hplayer.playlist.on('nomedia')`.
- **Act** by emitting an engine command (`hplayer.emit('play', …)`), changing a setting
  (`hplayer.settings.set('loop', 2)`), or calling a method directly (`hplayer.playlist.next()`).

The handler signature is always `(ev, *args)` — `ev` is the event string that fired, `*args` are the
values the source attached.

---

## 5 · Run

```python
hplayer.run()
```

Starts the players, samplers and interfaces (each on its own thread), waits for them to become ready,
emits `app-ready` then `app-run`, and **blocks** until shutdown. Put your "go" logic in a lifecycle
hook (next section), not after `run()` — code after `run()` won't execute until the program exits.

---

## Lifecycle hooks (important)

The engine emits these events; patch them to initialise and clean up at the right moment:

| Event | When | Use it for |
|-------|------|-----------|
| `app-ready` | players/interfaces have started and reported ready | early setup that needs components alive |
| `app-run` | the run loop has been entered | **your "go": set settings, start playback** |
| `app-closing` | shutdown has begun | stop timers, release resources |
| `app-quit` | final teardown | last-chance cleanup |

> **Gotcha:** don't start playback at import time — the player isn't running yet. Do it from
> `app-run`:

```python
@hplayer.on('app-run')
def start(ev, *args):
    hplayer.settings.set('volume', 100)
    hplayer.settings.set('loop', 2)          # 2 = loop the whole playlist
    hplayer.playlist.play('/data/usb')       # load a folder and start
```

---

## Controlling playback

Two complementary ways to drive media:

**A — engine commands** (fire-and-forget over the bus):

```python
hplayer.emit('play')           # play / resume
hplayer.emit('playpause')      # toggle
hplayer.emit('stop')
hplayer.emit('next')           # next track in the playlist
hplayer.emit('prev')
hplayer.emit('volinc', 5)      # nudge volume up
hplayer.emit('seek', 30000)    # ms (check the handler for exact arg semantics)
```

**B — the playlist object** (when you want the return value / direct control):

```python
hplayer.playlist.play('/data/usb')      # load a folder (or file) and play
hplayer.playlist.playindex(0)           # play a specific index
hplayer.playlist.next()                 # advance
hplayer.playlist.add('/data/clip.mp4')  # build a list programmatically
hplayer.playlist.clear()
hplayer.playlist.randomize()
i = hplayer.playlist.findIndex('intro*')  # glob-style lookup
```

**Settings** persist and drive the players automatically — set them, and players react:

```python
hplayer.settings.set('volume', 80)      # 0–100
hplayer.settings.set('mute', True)
hplayer.settings.set('loop', 1)         # -1 once · 0 no loop · 1 loop one · 2 loop all
hplayer.settings.set('flip', True)      # flip image (rotate 180°)
```

---

## Worked examples

### Minimal auto-looper (the `looper` profile)

```python
from core.engine.hplayer import HPlayer2

hplayer = HPlayer2(mediaPath='/data/usb')
player  = hplayer.addPlayer('mpv', 'looper')

@hplayer.on('app-run')                       # go
def init(ev, *args):
    hplayer.settings.set('volume', 100)
    hplayer.settings.set('loop', 2)
    hplayer.playlist.play('/data/usb')

@hplayer.playlist.on('nomedia')              # no media found → retry
def retry(ev, *args):
    from time import sleep
    sleep(1)
    hplayer.playlist.play('/data/usb')

hplayer.run()
```

### Keyboard + OSC + Web UI controller

```python
from core.engine.hplayer import HPlayer2

hplayer = HPlayer2(mediaPath='/data/media', config='/data/ctrl.cfg')
player  = hplayer.addPlayer('mpv', 'player')

hplayer.addInterface('keyboard')
hplayer.addInterface('osc', 4000, 4001)
hplayer.addInterface('http2', 8080)          # open http://<device>:8080

@hplayer.on('keyboard.KEY_SPACE-down')
def _(ev, *a): hplayer.emit('playpause')

@hplayer.on('keyboard.KEY_RIGHT-down')
def _(ev, *a): hplayer.emit('next')

@hplayer.on('osc.play')                       # incoming OSC '/play 2'
def _(ev, *a): hplayer.playlist.playindex(int(a[0]) if a else 0)

hplayer.run()
```

### GPIO trigger (Pi only, degrades elsewhere)

```python
from core.engine.hplayer import HPlayer2

hplayer = HPlayer2(mediaPath='/data/usb')
player  = hplayer.addPlayer('mpv', 'player')

if hplayer.isRPi():
    hplayer.addInterface('gpio', [16], 200, 0, 'PUP')   # GPIO16, debounce 200ms, pull-up

@hplayer.on('gpio.16-on')                     # button on pin 16 pressed
def trig(ev, *args):
    hplayer.playlist.playindex(0)

@hplayer.on('app-run')
def init(ev, *args):
    hplayer.settings.set('loop', 1)           # loop the triggered clip

hplayer.run()
```

### Synchronized multi-device (sketch)

```python
hplayer = HPlayer2(mediaPath='/data/sync')
player  = hplayer.addPlayer('mpv', 'player')
hplayer.addInterface('zyre', 'eth0')          # P2P discovery + synced triggers on eth0

@hplayer.on('zyre.event')                     # a trigger received from a peer
def on_peer(ev, *args):
    ...                                        # act on the synced cue
```

Multi-device sync (Zyre triggers, MTC/`nowde` continuous lock) is the deepest topic — study
[`profiles/multisync.py`](../profiles/multisync.py) and the upcoming `docs/sync.md`. The current
trigger→frame timing gap and the planned dual-mode (preroll + freewheel) convergence are described in
[`ROADMAP.md`](../ROADMAP.md) Phase 3.

---

## Reference appendix

### Engine command verbs (emit with `hplayer.emit('<verb>', …)`)

Confirmed handlers in `core/engine/hplayer.py`. Argument signatures vary per verb — confirm against
the handler or a working profile.

- **Playback:** `play` · `playpause` · `pause` · `resume` · `stop` · `next` · `prev` · `skip` ·
  `seek` · `playindex` · `playpauseindex` · `playonce` · `playloop` · `playpauseloop` · `playonce` ·
  `playthen` · `playpausethen` · `playstream` · `playtext` · `playpausetext` · `resumesync` ·
  `hardreset`
- **Playlist:** `add` · `remove` · `clear` · `load` · `do-playlist` · `do-playseq`
- **Loop:** `loop` · `unloop`
- **Volume / audio:** `volume` · `volinc` · `voldec` · `mute` · `unmute` · `pan` · `audiomode` ·
  `audioout`
- **Image / display:** `flip` · `unflip` · `brightness` · `contrast` · `filter` · `fade` · `unfade`
- **Misc:** `get-settings`

> `do-<key>` events (`do-volume`, `do-loop`, `do-flip`, …) are emitted *by* `Settings` whenever a key
> changes; players listen to them. You normally emit the bare verb (e.g. `volume`) or call
> `settings.set('volume', …)`, and the `do-` event flows downstream.

### Settings keys & defaults (`core/engine/settings.py`)

| Key | Default | Notes |
|-----|---------|-------|
| `volume` | `100` | 0–100 |
| `mute` | `False` | |
| `loop` | `0` | `-1` once · `0` no loop · `1` loop one · `2` loop all |
| `autoplay` | `False` | play automatically when the playlist updates |
| `flip` | `False` | rotate image 180° |
| `pan` | `[100, 100]` | L/R balance |
| `audioout` | `'jack'` | output device |
| `audiomode` | `'stereo'` | |
| `brightness` | `100` | |
| `contrast` | `50` | |
| `filter` | `''` | |
| `playlist` | `None` | last playlist (persisted) |

### Common events to listen for

- **Player:** `ready` · `playing` · `paused` · `stopped` · `media-end`
- **Playlist:** `nomedia` · `end` · `updated`
- **Engine lifecycle:** `app-ready` · `app-run` · `app-closing` · `app-quit`
- **Interfaces:** see each interface in [`interfaces.md`](interfaces.md)
  (e.g. `osc.<address>`, `gpio.<pin>-on`, `keyboard.<KEY>-down`, `midictrl.noteon`).

### Player methods (on the object returned by `addPlayer`)

`play(media, pause=False)` · `stop()` · `pause()` · `resume()` · `seekTo(ms)` · `skip(ms)` ·
`speed(s)` · `status()` · `isPlaying()` · `isPaused()` · `position()` · `addOverlay('rpifade', …)`.

---

## Tips & gotchas

- **Initialise from `app-run`, not at import time** — the player isn't running until `run()` starts it.
- **Guard hardware with `hplayer.isRPi()`** so the same profile stays portable; a missing interface
  returns `None` rather than crashing, but skipping the `addInterface` keeps logs clean.
- **Paths**: example profiles hard-code `/data/usb`, `/data/media`, `/data/sync`. These are
  conventions on the deployed Pis, not requirements — point `mediaPath` wherever your media is.
- **Multiple players**: add more than one and let extension-routing pick the backend per file.
- **Keep a reference** to objects you'll patch or call directly (`player = hplayer.addPlayer(...)`,
  `osc = hplayer.addInterface('osc', …)`).
- **Look at neighbours**: `profiles/` has many real examples (sync, GPIO, MIDI, MQTT remotes). Copying
  a close one is the fastest way to start.

---

*This is a living document. Once the engine refactor lands (ROADMAP Phase 2), command signatures and
event names will be declared in code and this guide should be regenerated/verified against them.*
