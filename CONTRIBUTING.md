# Contributing to HPlayer2

Thanks for helping out! HPlayer2 is a modular media player for live shows and installations, run on
Raspberry Pi, N100 mini-PCs, and Ubuntu/macOS desktops. This is a short, living guide — it will grow
as the project's architecture settles (see [`ROADMAP.md`](ROADMAP.md)).

## Get oriented

Before changing code, skim the docs — they'll save you reverse-engineering time:

- [`docs/architecture.md`](docs/architecture.md) — how the engine, players, interfaces, overlays and
  the event bus fit together.
- [`docs/interfaces.md`](docs/interfaces.md) — the I/O modules and their events.
- [`docs/profiles.md`](docs/profiles.md) — how shows are composed (the main customization surface).
- [`ROADMAP.md`](ROADMAP.md) — current priorities and where things are heading.

## Dev setup

This project uses [`uv`](https://docs.astral.sh/uv/). The ZeroMQ helpers (`czmq`, `zyre`) are
vendored under `scripts/` and need a one-time bootstrap:

```bash
python scripts/bootstrap_native_deps.py
export PKG_CONFIG_PATH="$HOME/.local/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
uv sync --extra dev          # installs runtime + dev tools (ruff, pytest)
uv run ruff check            # lint
uv run pytest                # tests
```

Then run a profile: `./hplayer2 default` (or any file in `profiles/`). Raspberry-Pi-only
dependencies (GPIO, evdev) install automatically on ARM Linux.

## Before you open a PR

- **Lint & test:** `uv run ruff check` is clean and `uv run pytest` passes. Add a test when it's
  reasonable (engine logic, parsing, settings/playlist behaviour) — test coverage is thin and
  welcome.
- **Keep it cross-platform.** The same code runs on Pi / N100 / desktop. If a feature needs specific
  hardware or a library, **fail soft**: detect the missing dependency and disable that piece (log a
  clear line), don't crash. Guard Pi-only paths (`hplayer.isRPi()`, import guards).
- **Mind the profile API.** Profiles in `profiles/` are deployed in the field. Avoid breaking the
  profile-facing API (`addPlayer` / `addInterface` / `on` / `emit`) casually; if you must, note it and
  update the affected profiles.
- **Match the surrounding style.** Follow the conventions of the file you're editing; `ruff` handles
  formatting/lint (line length 100, see `pyproject.toml`).
- **Describe the why.** In the PR, say what problem it solves and how you tested it (which platform,
  which profile).

## Bigger changes

The architecture is actively evolving (engine refactor, interface framework, sync convergence,
backend benchmarking — see the roadmap). For anything substantial — touching the engine core, the
sync paths, the event model, or adding a backend — **open an issue or discussion first**. These
decisions aren't locked yet, and your use case should help shape them rather than be retrofitted.

## Adding things

- **A new interface:** drop `core/interfaces/<name>.py` with a `class <Name>Interface(BaseInterface)`;
  it's then usable as `addInterface('<name>', ...)`. Follow an existing interface for the lifecycle
  pattern, declare your dependencies with an import guard, and document it in `docs/interfaces.md`.
- **A new player backend:** `core/players/<name>.py` with `class <Name>Player(BasePlayer)`, usable as
  `addPlayer('<name>', ...)`. Implement `validExt()` and the playback methods.
- **A new profile/example:** add it under `profiles/`. Keep genuinely reusable examples clear and
  minimal.

Questions and help requests are welcome via issues. PRs of any size are appreciated.
