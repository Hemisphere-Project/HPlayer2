# HPlayer2
HPlayer2 is a modular media player designed to allow multiple ways of control, over multiple platform.

It is build in a modular way: you can choose the player engine (mpv, vlc, omxplayer, ...),  
i/o interfaces (osc, http, rfid, ble, gpio, ...) and patch everything up.

HPlayer2 is focused on Raspberry Pi, but is based on python code wrapping 3rd parties engines and libraries, so as long as those 3rd parties components are supported on other platform, HPlayer2 should run on it !

## Supported Platforms

- Raspberry Pi 3B+ (and newer) running a recent Linux distribution
- x64 Linux distributions with mpv or alternative media engines available

Some interfaces depend on Raspberry Pi specific peripherals (GPIO, I2C devices, etc.). These modules now detect missing hardware gracefully so the same codebase can run on generic x64 systems. Optional engines or interfaces can remain disabled if the host platform does not expose the required capabilities.

HPlayer2 is under development, some features might not be fully available or sometimes broken, feel free to ask for help and open issues, i'll do my best to cover it. Pull requests are also welcomed !

## Media engine
Hplayer2 abstracts the concept of player (media list, play, pause, stop, volume, position, ...),
and then bind to an existing player engine.

On Raspberry Pi, i only managed to use 3 engines with Hardware acceleration on H.264 decoding:
 - omxplayer: the original HPlayer was based on via ofxOMXPlayer, but using OF on Pi was a bit tricky at the time
 - vlc: works great, but was tricky to compile on RPi when i tried it couple years ago
 - mpv: used to have a great build script, works very well and offers ipc interface to communicate with

The goal of HPlayer2 is to offer the choice between those 3 engines, but for now only **mpv** is fully supported.

## Install
HPlayer2 is a python program, with several "modular" dependencies, depending on which component you will be using.  
The core component you need to install is of course the media engine.
For now, only **mpv** is supported, so you should install it, but the **mpv** package in your distro repository might not be compiled with HW video decoding, so it might be necessary to build it yourself with this specific options enabled.

There are helper scripts to prepare the platform-specific prerequisites:

- `scripts/install_dependencies.sh` covers the legacy Raspberry Pi flows and supports **arch** and **xbian** (Raspbian/Debian/Ubuntu). It installs system packages and will call into `install_mpv.sh` for the hardware-accelerated build when the distro package does not provide it.
- `scripts/install_mpv.sh` detects prebuilt MPV binaries and, if needed, recompiles MPV with Raspberry Pi hardware acceleration enabled.
- `scripts/install_macos.sh` streamlines a macOS development setup. It leverages Homebrew to pull `uv`, autotools, `zeromq`, and then runs the Python bootstrapper described below before syncing the uv environment with the `dev` extra enabled.

Feel free to dive into the scripts and tweak them for your needs. If you want to help make installation more universal, please submit a PR!

On a freshly configured Raspberry Pi:

```bash
cd ~
git clone https://github.com/Hemisphere-Project/HPlayer2.git
cd HPlayer2/scripts
sudo ./install_dependencies.sh
sudo ./install_mpv.sh
cd ..
```

On macOS for local development you can run:

```bash
git clone https://github.com/Hemisphere-Project/HPlayer2.git
cd HPlayer2
./scripts/install_macos.sh
```

You should examine the scripts to understand what they do. You can also run each step manually instead of executing the script end to end—this helps when a dependency changes upstream (it can happen!).

## Development Setup

This project uses [uv](https://docs.astral.sh/uv/latest/) to manage the virtual environment.

ZeroMQ helper libraries (`czmq` and `zyre`) are vendored under `scripts/` via git sub-clones. Run the bootstrap script once (and whenever you need to update the native libraries):

```bash
python scripts/bootstrap_native_deps.py
export PKG_CONFIG_PATH="$HOME/.local/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
uv sync --extra dev
uv run ruff check
uv run pytest
```

The `dev` extra bundles the tools required for linting and testing. Raspberry Pi specific dependencies (GPIO and evdev bindings) are pulled in automatically on ARM Linux platforms. `ruff` performs lightweight linting and formatting, while `pytest` runs the unit test suite. All commands stay inside uv—no global installs required.

## Run
Since HPlayer2 is modular, the concept is to run HPlayer2 against a specific **profile**.
This **profile** links i/o interfaces to the media engine.  
There is a default profile provided, and several example based on projects where i use HPlayer2.

To start, go to HPlayer2 directory, and run `./hplayer2 profile`  
where *profile* is the name of a file in the **profiles** subdirectory (without the .py)

for exemple you can run `./hplayer2 bloffique`   
which will start HPlayer with the profile located in **profiles/bloffique.py**

if you omit the profile and simply run `./hplayer2`  
it will use the default profile located in **profiles/default.py**

To create a custom profile for your project, 
you can create a new file like **profiles/your-project.py**
To run it: `./hplayer2 your-project`

### MPV backend

The default player relies on [mpv](https://mpv.io/). On hosts where the binary is not installed in the `$PATH`, set `HPLAYER_MPV_BIN` to the desired executable. If `mpv` is missing entirely, HPlayer2 will attempt to use one of the prebuilt binaries located in `bin/prebuilds/` based on the current architecture.


## Patch a profile
The idea here is for you to program you own profile !  
(or to use an existing one if it feats your needs..)

Start reading the files in **profiles/** to see examples on how profiles are made.  
It's very simplified and *patching* oriented: an interface event can be plugged to a player action and vice-versa.

The best starting point is to read the default profile in **profiles/default.py**

The idea in a profile is:
 - create a player
 - attach interfaces modules (OSC, HTTP, RFID, GPIO, ...)
 - patch events from interfaces to action on the player (NB: some events are already patched automatically)
 - run


## Interfaces
HPlayer2 ships a broad set of **interface modules** — the I/O bridges between the player and the
outside world (networks, controllers, sensors, screens). They are optional and pluggable: a profile
enables only what it needs, and an interface whose library or hardware is missing simply stays
disabled (it won't crash the program), so the same profile can run on a Raspberry Pi, an N100, or a
desktop.

📖 **Full reference: [`docs/interfaces.md`](docs/interfaces.md)** — every interface's constructor
arguments, dependencies, platform support, and the events it emits, with examples.

Interfaces live in **core/interfaces/** and need no explicit import — add one in a profile with
`hplayer.addInterface('name', ...)` and patch its events with `@hplayer.on('name.event')`.

Available interfaces:
 - **osc** — OSC over UDP (TouchOSC, Max/MSP, lighting desks)
 - **http** / **http2** — basic HTTP API / responsive WebSocket web UI
 - **mqtt** — MQTT pub/sub bridge (e.g. ESP remotes, home automation)
 - **zyre** — ZeroMQ/Zyre P2P discovery + synchronized triggers (multi-device shows)
 - **regie** — multi-peer web control surface
 - **midictrl** / **mtc** / **nowde** — MIDI control surface / MIDI Time Code / continuous MTC sync
 - **gpio** / **hcon** — Raspberry Pi GPIO inputs & outputs
 - **keypad** — Adafruit LCD+button RPi shield ([like this](https://www.adafruit.com/product/1110))
 - **nfc** — PN532 RFID/NFC tag reader ([like this](https://www.adafruit.com/product/364))
 - **keyboard** — USB keyboard, numpad, or infrared remote ([like this](https://goo.gl/sz7rie))
 - **serial** / **btserial** / **teleco** — serial / Bluetooth / Arduino remote controls
 - **ticker** — internal metronome for timed triggers

For the bigger picture — how interfaces, players, overlays and the event bus fit together — see the
**[architecture overview](docs/architecture.md)**.


## CREDITS
HPlayer2 is developed by Thomas BOHL for [Hemisphere](https://www.hemisphere-project.com/) and [KXKM](https://kxkm.net/)

HPlayer2 is build on top of MPV player, liblo, Adafruit libs, ZeroMQ and more.. thanks to all those open developers !
