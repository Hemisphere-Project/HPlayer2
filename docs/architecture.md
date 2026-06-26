# HPlayer2 — Architecture Overview

> **Status: first draft.** Reconstructed by reading `core/` (the codebase has almost no docstrings).
> Accurate as of 2026-06-25; please correct anything that drifts from the code. For the planned
> evolution of this architecture, see [`ROADMAP.md`](../ROADMAP.md).

HPlayer2 is a **modular, event-driven media player** for live performance and installations. A small
engine orchestrates pluggable **players**, **interfaces**, and **overlays**, all wired together by a
user-authored **profile**. Everything communicates over a single **event bus**.

---

## Contents

- [The big picture](#the-big-picture)
- [Bootstrapping: launcher → profile → run](#bootstrapping-launcher--profile--run)
- [The engine (`HPlayer2`)](#the-engine-hplayer2)
- [The event bus](#the-event-bus)
- [Players](#players)
- [Engine components](#engine-components)
- [Interfaces](#interfaces)
- [Overlays](#overlays)
- [Lifecycle & threading](#lifecycle--threading)
- [Source layout](#source-layout)
- [Design notes & where this is heading](#design-notes--where-this-is-heading)

---

## The big picture

```
   profiles/<name>.py            ← you write this: build the graph, then run()
        │  creates
        ▼
┌─────────────────────────────────────────────────────────────────┐
│                          HPlayer2  (engine)                       │  core/engine/hplayer.py
│   event bus (root)  •  command handlers  •  active-player routing │
│   ┌──────────────┬───────────────┬───────────────┬────────────┐  │
│   │ Settings     │ Playlist      │ FileManager   │ Sampler     │  │  core/engine/*
│   │ (persisted)  │ (media list)  │ (disk + watch)│ ImGen Network│  │
│   └──────────────┴───────────────┴───────────────┴────────────┘  │
└───────┬───────────────────┬──────────────────────────┬───────────┘
addPlayer│          addInterface│                 addOverlay│
        ▼                    ▼                          ▼
 ┌──────────────┐   ┌──────────────────────┐   ┌──────────────────┐
 │ Players      │   │ Interfaces           │   │ Overlays         │
 │ mpv (default)│   │ osc http http2 mqtt  │   │ rpifade          │
 │ gst omx jp   │   │ zyre regie midictrl  │   │ rpiopengles      │
 │ midi videonet│   │ mtc nowde gpio nfc…  │   │ (screen / GL)    │
 └──────────────┘   └──────────────────────┘   └──────────────────┘
   3rd-party engines   protocols / hardware        display layers
```

Three mental models capture the whole system:

1. **Composition**: a profile *composes* one or more players + interfaces + overlays onto the engine.
2. **Events**: components never call each other directly — they **emit** and **listen** on the bus.
3. **Routing**: player commands (e.g. `play <file>`) are routed to the right backend by **file
   extension**, and feedback (`playing`, `media-end`, …) bubbles back out to interfaces.

---

## Bootstrapping: launcher → profile → run

```
./hplayer2 <profile>   →   launcher.py   →   import profiles.<profile>   →   hplayer.run()
```

- `hplayer2` (shell) and `launcher.py` resolve a **profile name** (default falls back to `looper`)
  and do `__import__("profiles." + profile)`.
- Importing the profile module *is* the program: the profile constructs an `HPlayer2`, adds a player,
  adds interfaces, patches events, and calls `hplayer.run()` (which blocks until shutdown).

A minimal profile (`profiles/default.py`):

```python
from core.engine.hplayer import HPlayer2

hplayer = HPlayer2(...)                       # the engine (media paths + config)
player  = hplayer.addPlayer('mpv', 'player')  # a backend, by name
hplayer.addInterface('keyboard')              # I/O modules
hplayer.addInterface('osc', 4000, 4001)
hplayer.addInterface('http2', 8080)

@hplayer.on('keyboard.KEY_KPPLUS-down')       # patch an interface event…
def _(ev, *a): hplayer.emit('volinc', 1)      # …to an engine command

hplayer.run()                                 # start everything, block
```

See [profile authoring](profiles.md) for a deeper guide.

---

## The engine (`HPlayer2`)

`core/engine/hplayer.py` — the central object (`class HPlayer2(Module)`). Responsibilities:

- **Owns the components**: ordered maps of `_players`, `_samplers`, `_interfaces`, plus the
  `Settings`, `Playlist`, `FileManager`, `ImGen` engine modules.
- **Is the root of the event bus** (its `parent` is `None`); every other component is a child whose
  events bubble up to it.
- **Command handlers**: binds the engine's verbs — `play`, `stop`, `pause`, `next`, `volinc`,
  `do-play`, `do-playlist`, … — to actions on the active player/playlist.
- **Active-player routing** (see [Players](#players)).
- **Paths & data dir**: takes media search path(s) and a config/settings file. The data directory
  defaults to a cross-platform location via `platformdirs.user_data_dir("HPlayer2", "Hemisphere")`
  (a temp dir is created under it). The constructor supports both a newer keyword API
  (`mediaPath`, `config`, `datadir`, `extraMediaPath`) and an older positional one
  (`basepath`, `settingspath`) via a backward-compat shim.
- **Lifecycle**: `run()` starts everything and blocks; `request_shutdown()` / signal handling drives
  graceful teardown.

### Pluggable by naming convention

All three plugin families resolve a short **name** to a class by the same convention — import
`core.<family>.<name>` and grab `<Name>Player` / `<Name>Interface` / `<Name>Overlay`
(`.title()`-cased name + suffix). If the import or class is missing, or the constructor raises
`RuntimeError` (missing dependency/hardware), the engine **logs and returns `None`** instead of
crashing:

| Family | Added with | Loader | Example mapping |
|--------|-----------|--------|-----------------|
| Player | `hplayer.addPlayer('mpv', 'name')` | `core/players/__init__.py` | `mpv → MpvPlayer` |
| Interface | `hplayer.addInterface('osc', …)` | `core/interfaces/__init__.py` | `osc → OscInterface` |
| Overlay | `hplayer.addOverlay('rpifade', …)` | `core/overlays/__init__.py` | `rpifade → RpifadeOverlay` |

This soft-fail is what makes one profile portable across Pi / N100 / desktop.

---

## The event bus

Every component subclasses `Module` (`core/module.py`), which wraps a `pymitter` `EventEmitter`
(wildcard-enabled, `.`-delimited). Two rules define the whole protocol:

1. **Emit & bubble.** When a component emits event `E`, it is delivered to local listeners *and*
   re-emitted on its parent as **`<componentname>.E`** (the component name, lower-cased). Since the
   engine is the root, an event from the `keyboard` interface reaches the engine as `keyboard.E`.
   (`module.py:41-48`)
2. **Patch with `on`.** Listen with the `@<component>.on('event')` decorator; handlers always have
   the signature `(ev, *args)`. Wildcards work: `@hplayer.on('osc.*')`, `@hplayer.on('*.media-end')`.

```
[osc] emit 'play'  ──bubble──▶  engine sees 'osc.play'
                                     │  (profile patch)
                                     ▼
                                hplayer.emit('play', …)  ──▶ command handler ──▶ activePlayer.play()
                                     │
player emits 'playing'/'media-end' ──bubble──▶ engine 'player.playing' ──▶ http2/zyre update UI/peers
```

Two flavors of events flow on this bus:

- **Commands** — imperative verbs the engine handles: `play`, `stop`, `pause`, `volinc`,
  `do-play`, `do-volume`, … (`do-<key>` events come from `Settings`; see below).
- **Notifications** — state changes a component announces: players emit `playing`, `paused`,
  `stopped`, `media-end`, `ready`; interfaces emit their inputs (`osc.<addr>`, `gpio.<pin>-on`, …).

> There is no central registry of event names yet — they're string literals across the codebase.
> Cataloguing them is ROADMAP item D3 (Phase 2).

---

## Players

A **player** is a thin wrapper around a media engine, all implementing the `BasePlayer` contract
(`core/players/base.py`): `start`, `play`, `stop`, `pause`, `seek`, volume/flip/etc., plus a
`validExt()` declaring which file extensions it handles and a `_status` dict surfaced via `status()`.

Backends (`core/players/`):

| Player | Engine / output | Notes |
|--------|-----------------|-------|
| `mpv` | mpv subprocess | **primary**; controlled over a Unix socket using **JSON IPC** |
| `gst` | GStreamer | alternative pipeline (used by `kabinGST` profile) |
| `omx` | omxplayer | legacy Pi backend |
| `jp` | just-playback | audio-only |
| `midi` | MIDI out (`mido`) | sends MIDI instead of A/V |
| `videonet` | ArtNet/DMX (UDP) | drives LED fixtures from frames |
| `mpvstream` | mpv (network stream) | streaming variant |

### Active player & extension routing

Multiple players can coexist (e.g. mpv for video + jp for audio). On a `do-play <file>` the engine
walks its players and dispatches to the **first one whose `validExt(file)` matches**, stopping the
previously-active player if it changes; the chosen index is remembered as `_lastUsedPlayer`, and
`activePlayer()` returns it (`hplayer.py:638`, `:256`). Settings (volume, mute, pan, flip, …) are
bound to each player when it's added, via `Settings`' `do-<key>` events.

### mpv backend specifics

`MpvPlayer` (`core/players/mpv.py`) spawns `mpv` and talks to it over a Unix domain socket with
mpv's JSON IPC protocol — sending commands like `loadfile`/`set_property` and polling properties
(`pause`, `core-idle`, `eof-reached`, …) back into the `_status` dict, which it re-emits as
`playing`/`paused`/`media-end` notifications. (Robustness caveats — socket cleanup, string-built
JSON — are tracked in the ROADMAP bugs backlog.)

---

## Engine components

Found in `core/engine/`, these are `Module`s the engine owns directly:

- **Settings** (`settings.py`) — persistent key/value store (JSON on disk). On `set()`/`load()` it
  emits `do-<key>` events that drive players (volume, mute, pan, flip, loop, autoplay, …). Keys are
  not yet schema-validated.
- **Playlist** (`playlist.py`) — the ordered media list and play cursor, with loop modes
  (`-1` play one / `0` no loop / `1` loop one / `2` loop all). Reacts to `media-end` to advance.
- **FileManager** (`filemanager.py`) — enumerates media across the search path(s) and uses
  `watchdog` to refresh when files change on disk (e.g. after an upload).
- **Sampler** (`sampler.py`) — groups players for layered/sample-style triggering.
- **ImGen** (`imgen.py`) — renders text/emoji to PNG (e.g. on-screen messages) via Pillow.
- **Network** (`network.py`) — IP/SSID helpers used at startup and by network interfaces.

---

## Interfaces

Interfaces are the I/O modules (OSC, HTTP/Web UI, MQTT, Zyre, MIDI/timecode, GPIO, NFC, keyboard,
serial/Bluetooth, …). They subclass `BaseInterface` (`core/interfaces/base.py`), run a `listen()`
thread, and translate the outside world ↔ engine events. Because this is the project's broadest
surface, it has its own complete reference:

👉 **[`docs/interfaces.md`](interfaces.md)** — every interface, its constructor args, dependencies,
platform support, and emitted events.

The uniform robustness/cross-platform framework for interfaces is ROADMAP Phases 2 & 4.

---

## Overlays

Overlays (`core/overlays/`) are display layers composited with video output:

- **rpifade** — fade-to-black / brightness overlay.
- **rpiopengles** — an OpenGL ES / EGL rendering layer (shaders, GL effects) for the Raspberry Pi.

Like players and interfaces, they're added by name (`addOverlay('rpifade', …)`) and are Pi-oriented.

---

## Lifecycle & threading

**Startup** (`hplayer.run()`, `hplayer.py:419`):
1. log network IPs;
2. `start()` all players, then samplers, then interfaces (each spins up its own thread);
3. wait for players/samplers to report `isReady()` (respecting an early shutdown signal);
4. set `appReady` and emit `app-ready`; enter the run loop and block.

**Threading model.** Each player and interface owns its own thread (e.g. mpv's IPC reader loop, an
interface's `listen()` loop); they coordinate purely through the event bus. The engine itself is
mostly reactive — handlers fire on emitted events. (Consequences: some loops busy-wait or block
without timeouts, and shutdown/cleanup is uneven across components — see ROADMAP Phase 1.)

**Shutdown.** `request_shutdown()` (and OS signal handling) clears the run event so the loop exits;
components are asked to stop. Clean teardown is a known weak spot today (notably Zyre — `stop()`
currently hangs, `zyre.py:602`).

---

## Source layout

```
core/
├── module.py            # Module / EventEmitterX — the event-bus base class
├── engine/
│   ├── hplayer.py       # HPlayer2 — the engine (orchestration, commands, routing)
│   ├── settings.py      # persisted settings → do-<key> events
│   ├── playlist.py      # media list + cursor + loop modes
│   ├── filemanager.py   # disk enumeration + watchdog
│   ├── sampler.py       # grouped/layered players
│   ├── imgen.py         # text/emoji → PNG
│   └── network.py       # IP/SSID helpers
├── players/             # mpv (primary), gst, omx, jp, midi, videonet, mpvstream  + base.py, __init__.py loader
├── interfaces/          # osc, http, http2, mqtt, zyre, regie, midictrl, mtc, nowde,
│                        #   gpio, hcon, keypad, nfc, keyboard, serial, btserial, teleco, ticker  + base.py, loader
└── overlays/            # rpifade, rpiopengles  + base.py, loader

profiles/                # user-authored compositions (the customization surface)
launcher.py / hplayer2   # entry point: pick a profile and import it
```

---

## Design notes & where this is heading

What makes the architecture pleasant: a tiny composition API (`addPlayer`/`addInterface`/`on`/`emit`),
one uniform event bus, soft-failing plugins, and profiles as the customization surface.

Known rough edges (all tracked in [`ROADMAP.md`](../ROADMAP.md)):

- `HPlayer2` is a 830-line **god-object** to be split into managers/router (Phase 2).
- The **interface framework** lacks a uniform lifecycle, capability detection, reconnection, and
  clean shutdown (Phases 2 & 4).
- **Sync** (Zyre triggers + MTC/`nowde` continuous) has an unmodeled trigger→frame gap and is being
  converged into one dual-mode service (Phase 3).
- The **event vocabulary** is undocumented string literals → an event catalog (Phase 2).
- **Backends** are to be benchmarked (mpv vs GStreamer vs native) per platform (Phase 5).

*This is a living document — keep it in step with the code as the refactor lands.*
