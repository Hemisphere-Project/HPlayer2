# HPlayer2 — Roadmap

> A living document. It pairs a **north-star vision** with a **phased, prioritized backlog**, so
> that anyone — a user adapting a profile for their show, or a developer extending the core —
> can quickly understand where the project is, where it's going, and where to plug in.

This roadmap was produced from a full-codebase audit (engine, players, interfaces, sync, web UI,
profiles, build, tests, docs). Findings are concrete and reference `file:line`. Severities:
**🔴 high** (breaks/leaks in production), **🟠 med** (reliability/maintainability), **🟡 low** (polish).

---

## 1. Vision / North Star

HPlayer2 is a **modular, event-driven media player for live performance and installations**.
A small core orchestrates pluggable **players**, **interfaces**, and **overlays**; user-authored
**profiles** are the customization surface that wires them into a show.

Where we're heading:

- **One codebase, every target.** The same core runs identically on **Raspberry Pi 3B+**, **N100
  mini-PCs**, and **Ubuntu/macOS** desktops. Hardware-specific capabilities degrade gracefully when
  absent — never a hard failure on the "wrong" platform.
- **Robust, measurable synchronization.** Converge today's two sync paths (Zyre P2P triggers +
  MTC/`nowde` continuous correction) into **one sync service** that supports both *frame-locked
  preroll starts* and *gapless freewheel looping with continuous drift correction*, over **wifi or
  ethernet**, across **differently-clocked hardware** — and that **measures** the real
  trigger→frame gap instead of hoping.
- **A broad, robust I/O ecosystem.** The player must speak to *anything* a show throws at it —
  **MIDI, OSC, HTTP/WebSocket, MQTT, NFC/RFID, GPIO, LCD/keypad, serial/UART, Bluetooth, infrared
  remotes, ArtNet/DMX, screens/overlays** — through a large family of **optional interface
  modules**. Each interface is a first-class citizen: **robust** (clean lifecycle, error recovery,
  reconnection/hot-plug) and **cross-platform on its targeted devices**, degrading gracefully (and
  loudly enough to debug) when its hardware or library is absent rather than crashing the program.
- **Pluggable, benchmarked backends.** Keep `mpv` as the default, but treat the backend as a
  measured choice: **mpv vs GStreamer vs a native (C/C++) prototype**, benchmarked per platform,
  to maximize hardware-decode coverage on more SoCs.
- **A WebUI you'd actually use on a phone.** A modern, mobile-first per-device UI **and** a central
  multi-peer dashboard to drive a whole installation from one screen, with reliable large-file upload.
- **Documentation that makes you feel at home.** Architecture overview, interface/event reference,
  and a profile-authoring tutorial so a newcomer is productive in an afternoon.

**Design principles**
1. *Small core, rich profiles* — keep the engine lean; push show logic into profiles/examples.
2. *Graceful degradation* — a missing interface dependency (GPIO/MIDI/NFC/HW-decode) disables one
   feature with a clear log line, never the program.
3. *Uniform I/O contract* — every interface (input or output, network or hardware) follows the same
   lifecycle, declares its dependencies/capabilities, and handles reconnection and clean shutdown
   the same way. "Everything is an interface."
4. *Measure, don't guess* — sync, latency, and backend choices are backed by telemetry/benchmarks.
5. *Stable profile API* — internal refactors are shielded by a compatibility layer; profiles keep working.

---

## 2. Architecture today

```
                    ┌─────────────────────────────────────────────┐
                    │                  HPlayer2                    │  core/engine/hplayer.py
                    │   (event bus • command router • settings)    │  (pymitter EventEmitterX)
                    └───────┬───────────────┬──────────────┬───────┘
            addPlayer()     │               │ addInterface()│   addOverlay()
                            ▼               ▼              ▼
                 ┌──────────────┐  ┌──────────────────┐  ┌────────────┐
       Players → │ base.py      │  │ INTERFACES        │  │ OVERLAYS   │
                 │  mpv  (JSON  │  │  osc  http2  zyre │  │ rpifade    │
                 │  IPC/socket) │  │  nowde  mtc  gpio │  │ rpiopengles│
                 │  gst  omx jp │  │  keyboard midi …  │  └────────────┘
                 │  videonet …  │  └──────────────────┘
                 └──────┬───────┘
                        ▼
                  Playlist / FileManager / Settings / Sampler / ImGen
```

- **Event bus.** `core/module.py` defines `Module(EventEmitterX)` (pymitter, wildcard, `.`-delimited).
  Events bubble child → parent (`module.py:41-48`); interfaces/players auto-bind to the engine.
- **mpv backend.** `core/players/mpv.py` spawns `mpv` and talks to it over a Unix socket using
  JSON IPC; status (`playing`, `media-end`, `core-idle`, …) is polled back and re-emitted.
- **Profiles.** A profile (e.g. `profiles/default.py`) creates a player, adds interfaces, patches
  interface events to player actions, and calls `hplayer.run()`.

### The interface ecosystem (today)

Breadth is already a strength — ~19 interface modules plus output-side modules cover most live-show
I/O. The weakness is *uniformity*: each was hardened ad hoc, so robustness and cross-platform
behavior vary widely. `Dir` = direction (In/Out/Bidir). `Degrade` = guards missing dep/hardware and
keeps the program alive.

| Interface | Medium | Dir | Dep (lib / hardware) | Platforms | Degrade | Notable robustness gap (file:line) |
|-----------|--------|-----|----------------------|-----------|:------:|------------------------------------|
| osc | OSC/UDP | Bidir | python-osc | all | Y | no error trap in server loop (`osc.py:92`) |
| http | HTTP/REST | Bidir | stdlib (+zeroconf) | all | Y | no request timeout; blocks on shutdown |
| http2 | HTTP/WebSocket | Bidir | flask-socketio, PIL | all | Y | **`stop()` is a no-op** (`http2.py:375-377`); Flask thread never joins |
| midictrl | MIDI | In | python-rtmidi | Lin/mac/Win | Y | **best-in-class** backoff reconnect; unsafe `join` (`midictrl.py:169-176`) |
| mtc | MIDI timecode | In | mido, timecode | Lin/mac/Win | Y | no recovery if port fails after open (`mtc.py:50-89`) |
| nowde | MIDI TC (+OSC) | In | mido, timecode | Lin/mac/Win | Y | health-check reconnect; OSC bind hardcoded (`nowde.py:75`) |
| gpio | digital I/O | Bidir | RPi.GPIO | **Pi only** | Y | no listen-loop error handling; no pin-busy check (`gpio.py:50-74`) |
| keyboard | evdev / USB+IR | In | evdev, watchdog | **Linux** | Y | good hot-plug; no exception handling in read loop (`keyboard.py:75-138`) |
| keypad | I2C LCD + buttons | I/O | Adafruit_CharLCD | **Pi + I2C** | Partial | MockLCD fallback (good); no loop recovery (`keypad.py:88-120`) |
| nfc | I2C/SPI NFC | In | Adafruit_PN532 | **Pi only** | Y (load) | hard-fails on `begin()`; no hot-plug; loop can hang (`nfc.py:49-122`) |
| serial | UART/serial | In | pyserial | all | Y | no reconnect-on-error; hardcoded timeout (`serial.py:65,89-92`) |
| btserial | Bluetooth RFCOMM | I/O | pybluez | all (BT) | Y | partial reconnect; state lag after error (`btserial.py:98-109`) |
| mqtt | MQTT pub/sub | Bidir | paho-mqtt | all | Y | blocking connect loop; disconnect hangs on unplug (`mqtt.py:73-85`) |
| zyre | ZeroMQ/Zyre | Bidir | zyre, czmq | Lin/mac | Y | shutdown fragile (`stop()` commented, `zyre.py:602`); no parse guards |
| teleco | UART (Arduino) | I/O | pyserial | all | Y | no reconnect on `SerialException` (`teleco.py:126-128`) |
| hcon | GPIO (preset pins) | Bidir | RPi.GPIO | **Pi only** | Y | thin gpio wrapper; no extra handling |
| ticker | internal timer | Out | stdlib | all | Y | no drift compensation (`ticker.py:13-18`) |
| regie | HTTP/WS + filewatch | I/O | flask-socketio, watchdog | all | Y | project reload can fail silently (`regie.py:140`) |
| *videonet* (out) | ArtNet/DMX UDP | Out | stupidArtnet, numpy, cv2 | all | Y | net check before init; busy-wait timing (`videonet.py:88-89`) |
| *midi* (out) | MIDI out | Out | mido | Lin/mac/Win | Partial | no output-port error handling (`players/midi.py`) |
| *overlays* (out) | screen / GL / framebuffer | Out | rpiopengles, fbi | **Pi** (GL/fb) | — | Pi-specific render paths |

**`BaseInterface` today** (`core/interfaces/base.py`) provides a single `listen()` thread, a
`stopped` Event, `start()/quit()/isRunning()`, `autoBind`, and `log/emit`. It **lacks** the things
that would make robustness uniform: availability/health checks, a standardized reconnection/hot-plug
hook, guaranteed `try/finally` cleanup, a join timeout, an `error` event, runtime status, and
dependency/capability declaration. Result: ~12 recurring fragility patterns (no error trap in listen
loops, inconsistent shutdown, no capability detection, blocking I/O without timeout, no conformance
tests). This is exactly what **Phase 2** (framework) + **Phase 4** (ecosystem pass) address.

### The three sync paths (and where the gap is)

| Path | File | Model | Strength | Weakness |
|------|------|-------|----------|----------|
| **Zyre** | `core/interfaces/zyre.py` | P2P discovery + **discrete timestamped triggers** (`at` field), per-peer clock-shift estimate | Robust auto-discovery, wifi-friendly, good for cue triggers | **Trigger ≠ frame**: event fires, but playback starts 150–600 ms later; busy-wait timing adds jitter; no feedback |
| **nowde** | `core/interfaces/nowde.py` | **Continuous MTC** — adaptive speed correction, dead-zone hysteresis, smoothing, kickstart | Frame-accurate continuous lock (±1–2 frames) | Needs MIDI/MTC source; not wifi-native; wired |
| **mtc** | `core/interfaces/mtc.py` | Raw MTC quarter/full-frame receiver (`qf`/`ff` events) | Minimal building block | No correction logic on its own |

**The core problem to solve (Phase 3):** a Zyre trigger is emitted at `zyre.py:746`, but the actual
first frame/audio sample appears far later (mpv init + codec setup + A/V buffering + OS scheduling).
There is **no preroll** (preload + pause-on-first-frame) and **no measurement** of real onset, so the
trigger→frame gap is unmodeled. `nowde` solves continuous lock but is a separate, wired path. These
should converge.

---

## 3. Decisions & constraints

These were decided with the project owner and constrain the plan below:

- **Roadmap shape:** layered (this document) — vision + phased backlog.
- **Sync target — dual-mode:**
  - **Preroll-locked start:** preemptive command + preload + pause-on-first-frame, released on a
    shared clock; corrects missed triggers and speed variation across differently-clocked systems.
  - **Freewheel:** seamless gapless looping with continuous jitter/drift correction (no preroll).
  - Aim for **frame-locked precision**; tolerate slightly divergent startup when preroll isn't
    workable (e.g. instant-start).
- **Interface ecosystem is a co-priority** (alongside cross-platform player + sync): the breadth of
  protocols/mediums (MIDI, OSC, HTTP, MQTT, NFC, GPIO, serial, Bluetooth, IR, ArtNet, screens…) is a
  defining feature, so each optional interface gets a robustness + cross-platform pass and a uniform
  framework — not just the sync/webui ones.
- **Backend strategy:** **benchmark** mpv / GStreamer / native in parallel on RPi3B+ / N100 / desktop;
  implement or improve whichever is justified, behind the existing player abstraction.
- **Refactor freedom:** breaking engine/event/IPC changes are allowed **with a compatibility shim +
  profile migration**.
- **WebUI:** keep & modernize the **per-device** UI **and** add a separate **central multi-peer**
  dashboard. **nginx is optional** — used for large uploads / static asset serving, not required for
  simple Pi installs.
- **Cleanup:** **reorganize in-place** — introduce `examples/` + `archive/`, move prebuilt binaries
  to Git LFS / GitHub Releases, keep most things in-repo for reference. Year-numbered profiles
  (`24-`/`25-`/`26-`) are kept as examples.

---

## 4. Phased roadmap

Phases are sequenced by dependency, but per the owner's intent **all four audit dimensions start
early** (Phases 0–1 already touch bugs, cleanup, perf, and docs). Each phase lists goals, key tasks,
and exit criteria.

### Phase 0 — Foundations & quick wins
*Goal: unblock contributors and stop the bleeding before deeper work.*
- Fix the **broken install docs** — README points at `scripts/install_dependencies.sh` /
  `scripts/install_mpv.sh` which now live only in `scripts/_legacy/`; the real path is
  `install_xbian.sh` + `install_macos.sh` + `bootstrap_native_deps.py`. (`README.md:36-37`)
- Remove **launcher dead code** (`launcher.py:26-32`: `sys.exit(0)` before the import try/except).
- **Stop committing 125 MB of binaries** — `.gitignore` `bin/prebuilds/`, move them to Git LFS or
  GitHub Releases (downloaded by the bootstrap script).
- Stand up **CI**: `ruff check` + `pytest` on push (matrix: linux x64; add arm later).
- Add **doc scaffolding**: `docs/architecture.md`, `docs/interfaces.md`, `docs/sync.md`,
  `CONTRIBUTING.md` (stubs filled in Phase 7).
- **Exit:** a fresh clone on Linux & macOS installs and runs `default`/`looper` by following the
  README verbatim; CI is green.

### Phase 1 — Stability hardening
*Goal: make the current system rock-solid in production. (Owner Phase-1 focus.)*
- **Zyre shutdown** — `zyre.py:602` `stop()` is commented out ("HANGS!"); resolve clean teardown
  (orphaned threads/sockets). Closes the long-standing `TODO: close zyre: problem!`.
- **Playlist shared state** — `playlist.py:9-11` move `_playlist/_index/_lastran` into `__init__`
  (currently class attributes → shared across instances).
- **Resource leaks** — FileManager observers never stopped (`filemanager.py:96-99`); mpv socket not
  closed on retry/except (`mpv.py:197-213,336-341`); `thread.join()` without timeout.
- **Atomic settings** — write-temp-then-rename + debounce (`settings.py:104-107` writes on every `set()`).
- **Safe mpv IPC** — replace string-concatenated JSON with `json.dumps()` (`mpv.py:439+`) so paths
  with quotes/backslashes don't break playback.
- **HTTP2 upload hardening** — server-side size limit, error rollback on failed resize, atomic
  dedup, and a stoppable background thread (`http2.py:177-215,229-237`).
- **Kill busy-waits** — Zyre `preProcessor2` spin (`zyre.py:741`) and videonet frame spin
  (`videonet.py:88-89`) → sleep-to-near + short final spin.
- **Zyre Subscriber bug** — reconcile `self.interface` vs `self.node.interface` (`zyre.py:244,253-254`).
- **Exit:** 48-hour soak on a Pi with no fd/thread growth; clean shutdown (incl. Zyre); no corruption
  after kill-during-write.

### Phase 2 — Core & interface framework refactor (with compatibility shim)
*Goal: a maintainable core, and a uniform interface framework that makes every I/O module robust by
construction — without breaking deployed profiles.*
- **Split the god-object** `hplayer.py` (830 lines) into `PlayerManager`, `SamplerManager`,
  `CommandRouter`, `SettingsBinder`; remove per-player closure growth (`hplayer.py:193-224`).
- **Strengthen the `BaseInterface` framework** (`core/interfaces/base.py`) into the contract that the
  whole interface ecosystem (Phase 4) builds on: formal lifecycle (init → available? → start/listen →
  reconnect → stop/teardown), **dependency & capability declaration** (which lib/hardware an interface
  needs, queried before load), **standardized reconnection/hot-plug hooks**, **guaranteed resource
  cleanup**, and a uniform **health/status** signal. Apply the same lifecycle to `players/base.py`.
- **Settings schema + validation** (typed keys, ranges, no silent key creation).
- **Event catalog as code** — a single registry of event names/semantics (today they're string
  literals scattered across files).
- **Compatibility layer** — keep the profile-facing API (`addPlayer`, `addInterface`, `on(...)`,
  `emit(...)`) stable; migrate the curated/example profiles onto the new internals.
- **Exit:** all kept profiles run unchanged through the shim; core modules have lifecycle docstrings.

### Phase 3 — Sync convergence (flagship)
*Goal: one sync service, dual-mode, measurable, over wifi & ethernet. (Owner top priority.)*
- **Unified time service** — a shared monotonic clock + peer clock-shift estimation reused by both
  Zyre and MTC paths (today Zyre estimates shift, `nowde` ignores it).
- **Player preroll API** — `load → pause-on-first-frame → seek-ready → release` primitives in
  `players/base.py`, implemented for mpv (and any benchmarked backend).
- **Dual-mode sync engine** behind a single `sync` abstraction merging `zyre` + `nowde` + `mtc`:
  - **Preroll-locked start:** preemptive command, preload, hold on first frame, release on shared
    clock; correct missed triggers and inter-system speed drift.
  - **Freewheel:** gapless looping + continuous position/speed correction (the `nowde` algorithm,
    generalized to a network clock source, not just MIDI).
- **Sync telemetry** — measure *actual* frame/audio onset vs target and feed it back (close the
  loop the audit flagged at `zyre.py:746`); expose metrics to the WebUI.
- **Transport-agnostic** — same semantics whether the clock arrives via Zyre (wifi/ethernet) or
  MTC (MIDI), with an MTC-over-network bridge as an option.
- **Exit:** N heterogeneous nodes (Pi + N100) start a cue frame-locked with preroll, and loop
  gaplessly in freewheel; measured onset spread reported and within target.

### Phase 4 — Interface ecosystem: robust, cross-platform I/O
*Goal: make the breadth a strength — every optional interface is robust and cross-platform on its
targeted devices, built on the Phase-2 framework. (Owner co-priority.)*
- **Roll the framework across all ~19 interfaces** — wrap each `listen()` loop in standardized
  error handling, guaranteed cleanup, and a join-timeout; emit a uniform `error`/status event
  (today error reporting is inconsistent: `serial.py` emits `disconnected`, `osc.py` only logs).
- **Capability & dependency declaration** — each interface declares its lib/hardware needs and
  exposes `isAvailable()/isHealthy()` so a profile (or the WebUI) can probe at runtime instead of
  hard-coding; Pi-only modules (`gpio`, `nfc`, `hcon`, `keypad`) cleanly no-op and log on N100/desktop.
- **Reconnection / hot-plug pass per medium** — generalize the good patterns (midictrl backoff,
  keyboard evdev watchdog) to the weak ones: serial/btserial reconnect on unplug (`serial.py:89-92`),
  MIDI port appear/disappear, MQTT reconnect/backoff without hanging (`mqtt.py:84-85`), NFC reader
  presence (`nfc.py:54`), OSC port-in-use handling.
- **Health surfacing** — per-interface status (connected / degraded / unavailable) into logs and the
  central dashboard (Phase 6), so a missing remote or dead MIDI link is visible during a show.
- **Interface conformance test suite** — a shared harness that loads each interface on each target
  platform, with and without its hardware, and asserts: no crash, graceful degrade, clean shutdown,
  survives idle + device loss. (No such tests exist today.)
- **Curate & extend** — document the supported protocol/medium matrix; add the most-requested
  missing I/O only after the existing set is solid.
- **Exit:** every shipped interface loads on all target platforms without crashing, recovers from
  device loss where applicable, reports health, and passes the conformance suite.

### Phase 5 — Backend strategy (benchmark-driven)
*Goal: maximize HW-decode coverage per platform without guessing.*
- **Harden the player abstraction** so backends are interchangeable (lifecycle from Phase 2).
- **Benchmark harness** measuring startup latency, HW-decode coverage, CPU/GPU load, seek/loop-gap,
  and sync-preroll behavior for **mpv vs GStreamer vs a native prototype** on RPi3B+ / N100 / desktop.
  (GStreamer already partly exists — `players/gst.py`, used by `profiles/kabinGST.py`.)
- **Promote/improve** the winning backend per platform; document a **backend × platform matrix**.
- Evaluate a **native (C/C++) core** for the hottest paths (sync clock, decode glue) only if
  benchmarks justify it.
- **Exit:** documented matrix + a reproducible benchmark; each target platform has a recommended,
  HW-accelerated backend.

### Phase 6 — WebUI refactor (the flagship interface)
*Goal: a phone-friendly UI per device + one screen to rule the whole installation. (Owner focus.)*
- **Modernize per-device UI** (`http2`) — mobile-first, touch-friendly, lighter asset bundle
  (today it ships ~3.3 MB of FontAwesome/Bootstrap/jQuery in `core/interfaces/http2/res/`).
- **Central multi-peer dashboard** — evolve `regie` (`core/interfaces/regie.py` + `regie/index.html`)
  into a dashboard that discovers peers (via Zyre) and controls/monitors many devices at once,
  surfacing the Phase-3 sync telemetry.
- **Upload pipeline** — optional **nginx reverse proxy** for large/chunked/resumable uploads and
  static-asset serving; keep a pure-Python fallback for simple Pi installs.
- **Optional auth** — the current UI lets any LAN client control or delete media.
- **Exit:** drive a multi-device show from a phone; upload a multi-GB file reliably; per-device UI
  still works standalone.

### Phase 7 — Documentation completeness
*Goal: a newcomer feels at home. (Owner focus; biggest gap identified.)*
- **Architecture overview** (`docs/architecture.md`) — diagram, event flow, module responsibilities.
- **Interface & event reference** (`docs/interfaces.md`) — every interface: params, emitted events,
  hardware needs, platform support.
- **Profile-authoring tutorial** — from `default.py` to a custom show; decorator/event patterns.
- **Sync setup guide** (`docs/sync.md`) — preroll vs freewheel, clock sources, expected accuracy.
- **Platform tuning** — surface the (good but hidden) `extra/rpi-config/` settings (gpu_mem,
  scheduler, HDMI/audio) and desktop notes.
- **Troubleshooting** + **CONTRIBUTING** + settings/loop-mode reference.
- **Exit:** docs cover install, profiles, interfaces, sync, tuning, troubleshooting, contributing.

### Cross-cutting — Testing & CI
*Runs alongside all phases.*
- Integration tests against a headless mpv; a **sync-correctness harness**; profile-load smoke tests;
  CI matrix (x64 + arm). Today: 7 files / ~13 mostly error-path unit tests, no CI.

---

## 5. Detailed backlog by dimension

### 5.1 Bugs & issues
| # | Issue | Location | Sev | Phase |
|---|-------|----------|-----|-------|
| B1 | Playlist `_playlist/_index/_lastran` are class attrs → shared across instances | `core/engine/playlist.py:9-11` | 🔴 | 1 |
| B2 | `zyre.stop()` commented out ("HANGS!"), no clean teardown | `core/interfaces/zyre.py:602` | 🔴 | 1 |
| B3 | HTTP2 upload: no size limit, no rollback on resize fail, racy dedup | `core/interfaces/http2.py:177-215` | 🔴 | 1 |
| B4 | FileManager watchdog observers never stopped | `core/engine/filemanager.py:96-99` | 🔴 | 1 |
| B5 | mpv socket leak on retry/except | `core/players/mpv.py:197-213,336-341` | 🔴 | 1 |
| B6 | mpv JSON IPC built by string concat (no escaping) | `core/players/mpv.py:439+` | 🟠 | 1 |
| B7 | Settings written non-atomically, on every `set()` | `core/engine/settings.py:104-107` | 🟠 | 1 |
| B8 | HTTP2 background thread never stops (zombie) | `core/interfaces/http2.py:229-237` | 🟠 | 1 |
| B9 | Zyre Subscriber mixes `self.interface` / `self.node.interface` | `core/interfaces/zyre.py:244,253-254` | 🟠 | 1 |
| B10 | Zyre malformed-message `json.loads` uncaught | `core/interfaces/zyre.py:536-546` | 🟠 | 1 |
| B11 | launcher dead code after `sys.exit(0)` | `launcher.py:26-32` | 🟠 | 0 |
| B12 | README references missing install scripts | `README.md:36-37` | 🟠 | 0 |
| B13 | PIL `textsize()` deprecated (breaks on Pillow 10+) | `core/engine/imgen.py:34` | 🟠 | 1 |
| B14 | `thread.join()` without timeout (hang risk) | `mpv.py:421-427`, `jp.py:86-87` | 🟡 | 1 |
| B15 | Naive glob→regex, no escaping | `core/engine/filemanager.py:305-324` | 🟡 | 1 |
| B16 | Bare excepts swallow errors | settings/sampler/videonet/filemanager | 🟡 | 1 |
| B17 | Systemd hardcodes `WorkingDirectory=/opt/HPlayer2` | `hplayer2@.service` | 🟡 | 0 |

### 5.2 Code / architecture / files cleanup
| # | Item | Location | Phase |
|---|------|----------|-------|
| C1 | Split `HPlayer2` god-object (830 lines) into managers/router | `core/engine/hplayer.py` | 2 |
| C2 | Per-player setting closures grow unbounded, no cleanup | `core/engine/hplayer.py:193-224` | 2 |
| C3 | Define player/interface lifecycle + cleanup contracts | `players/base.py`, `interfaces/base.py` | 2 |
| C4 | Extract duplicated sync logic (~200 lines) into a shared module | `biennale24*.py`, `multisync.py` | 2 |
| C5 | Reorganize profiles: `examples/` (curated) + `archive/` (legacy) | `profiles/`, `profiles/_legacy/` | 0/2 |
| C6 | Remove duplicate profiles (kxkm/xpa appear active *and* legacy) | `profiles/` | 0 |
| C7 | Move `bin/prebuilds/` (~125 MB) to LFS/Releases; gitignore | `bin/prebuilds/`, `.gitignore` | 0 |
| C8 | Move `scripts/_legacy/`, `upgrades/` into `archive/`; document | `scripts/_legacy/`, `upgrades/` | 2 |
| C9 | Document/relocate `extra/arduino`, `extra/test`, `extra/lua` as companions | `extra/` | 2 |
| C10 | Reconcile "mpv only" README vs 9 real backends; document gst | `README.md`, `core/players/` | 7 |

### 5.3 Performance & tweaks
| # | Item | Location | Phase |
|---|------|----------|-------|
| P1 | Replace busy-wait sync spin with sleep-to-near + short spin | `core/interfaces/zyre.py:741` | 1/3 |
| P2 | Replace videonet frame busy-loop | `core/players/videonet.py:88-89` | 1 |
| P3 | Close trigger→frame gap with preroll + telemetry | `zyre.py:746`, `players/*` | 3 |
| P4 | FileManager: avoid full-tree rescan on every change; cache | `filemanager.py:26-31,247-328` | 1/2 |
| P5 | Settings `load()` shouldn't fire every `do-*` callback | `core/engine/settings.py:66-68` | 2 |
| P6 | Batch O(n) status aggregation per player update | `core/engine/hplayer.py:259-260` | 2 |
| P7 | Bound/timeout startup network-interface probing | `core/engine/hplayer.py:429-435` | 1 |
| P8 | Surface (don't change) the good Pi tuning as documented opt-in | `extra/rpi-config/` | 7 |

### 5.4 Documentation coverage
| # | Gap | Target | Phase |
|---|-----|--------|-------|
| D1 | No architecture overview / event-flow diagram | `docs/architecture.md` | 7 |
| D2 | No interface reference (params, events, hardware, platforms) | `docs/interfaces.md` | 7 |
| D3 | No event catalog (event names are scattered string literals) | code registry + docs | 2/7 |
| D4 | No sync setup guide (preroll/freewheel, clocks, accuracy) | `docs/sync.md` | 3/7 |
| D5 | No profile-authoring tutorial | `docs/profiles.md` | 7 |
| D6 | Settings keys/ranges, loop modes undocumented | `docs/` + docstrings | 7 |
| D7 | Backend × platform support matrix missing | `docs/backends.md` | 5 |
| D8 | No troubleshooting / FAQ, no CONTRIBUTING | `docs/`, `CONTRIBUTING.md` | 0/7 |
| D9 | Broken install instructions | `README.md` | 0 |

### 5.5 Interface ecosystem (robust, cross-platform I/O)
*Cross-dimension; this is the co-priority pillar. Phase 2 builds the framework, Phase 4 rolls it out.*
| # | Item | Location | Phase |
|---|------|----------|-------|
| I1 | `BaseInterface` has no availability/health check, reconnection hook, guaranteed cleanup, join-timeout, or `error` event | `core/interfaces/base.py:6-48` | 2 |
| I2 | No capability/dependency declaration — profiles hard-code which interfaces to load; can't probe at runtime | all interfaces | 2/4 |
| I3 | No error trap in `listen()` loops → an exception silently kills the interface thread | `osc.py:92`, `gpio.py:71`, `nfc.py:70`, `serial.py:78` | 4 |
| I4 | Inconsistent shutdown/cleanup (some join threads, some don't; some guard sockets, some don't) | `base.py:35`, `zyre.py:590`, `midictrl.py:169` | 4 |
| I5 | `http2.stop()` is a no-op; Flask thread never joins (also tracked as B8) | `http2.py:375-377` | 4 |
| I6 | No reconnect-on-error / hot-plug for serial & teleco; breaks and stays broken on unplug | `serial.py:89-92`, `teleco.py:126-128` | 4 |
| I7 | MQTT connect/disconnect can hang on device loss | `mqtt.py:73-85` | 4 |
| I8 | NFC hard-fails on `begin()`, no hot-plug, read loop can hang | `nfc.py:49-122` | 4 |
| I9 | Inconsistent error/status event emission (serial emits, osc/keyboard only log) → parent can't react uniformly | `serial.py:70`, `osc.py`, `keyboard.py:87` | 4 |
| I10 | Pi-only modules should cleanly no-op + log on N100/desktop (verify each) | `gpio.py`, `nfc.py`, `hcon.py`, `keypad.py` | 4 |
| I11 | No interface conformance test harness (idle survival, device-loss, clean shutdown, degrade) | `tests/` | 4 |
| I12 | Generalize the *good* patterns (midictrl backoff, keyboard evdev hot-plug) to the weak interfaces | midictrl/keyboard → others | 4 |

---

## 6. Repo reorganization map (in-place, non-destructive)

```
HPlayer2/
├── core/                      # unchanged location; refactored internally (Phase 2)
├── examples/                  # NEW — curated, working reference profiles (default, looper, multisync, a sync example)
├── profiles/                  # user/show profiles (year-numbered shows kept here as examples)
├── archive/                   # NEW — moved here for reference, out of the main flow
│   ├── profiles-legacy/       #   ← profiles/_legacy/*
│   ├── scripts-legacy/        #   ← scripts/_legacy/*
│   └── upgrades/              #   ← upgrades/* (per-show deploy scripts)
├── docs/                      # grows in Phase 7 (architecture, interfaces, sync, profiles, backends, tuning)
├── scripts/                   # install_xbian.sh, install_macos.sh, bootstrap_native_deps.py, vendored czmq/zyre
├── extra/
│   ├── rpi-config/            # documented as the Pi tuning reference (Phase 7)
│   ├── arduino/               # documented as companion firmware (consider separate repo later)
│   └── ...                    # test/lua experiments labelled clearly
└── bin/prebuilds/             # removed from git; fetched via LFS/Releases by bootstrap
```

Nothing is deleted outright in this map — legacy material moves to `archive/` and stays browsable.

---

## 7. Open questions / future considerations

- **Native core scope** — which hot paths (sync clock? decode glue?) would actually benefit from
  C/C++/Rust, gated on Phase-4 benchmarks.
- **MTC-over-network** — bridging continuous MTC semantics over Zyre/UDP so the wired-only path
  becomes wifi-capable.
- **Authentication model** — for the WebUI / central dashboard on shared networks.
- **Packaging** — a non-Pi install story (pipx/uv tool, container) for desktop users.
- **Profile API versioning** — how long the compatibility shim is supported and a deprecation policy.

---

*Maintained by the HPlayer2 team. Contributions welcome — see `CONTRIBUTING.md` (Phase 0). When you
fix a backlog item, link the PR next to it and check it off.*
