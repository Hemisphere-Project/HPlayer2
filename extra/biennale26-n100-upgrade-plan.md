# Biennale 26 — N100 fleet convergence plan (x86 track)

Surveyed 2026-07-21 on the bench LAN (all 8 units, `root@` + mgr agent key,
fallback `root:rootpi`). Companion of the RPi golden-reflash track — the ARM
image can't be dd'ed here, so the N100s converge **in place**. This is the
#t-020 deliverable, **v2 after Thomas's review** (2026-07-21); execution
waits for his confirmation.

## Objective (Thomas, 2026-07-21)

**Feature parity and compatible operation between N100 and RPi 3B+ players**
— same HPlayer2 code (latest `master`), same `biennale` profile, same
Pi-tools (latest `2026`), and above all the **same SYNC/WALL machinery**:
every unit (either hardware) must be switchable between SOLO and SYNC/WALL
per install case, through the same `/boot/wifi` marker convention and the
same webconf UI. No pinned "golden SHA" — both repos track their branch tip
at execution time; the deployed SHAs get recorded in the ledger.

## Decisions recorded (Thomas, 2026-07-21)

1. **SYNC roles**: not fixed per machine — both modes stay available on
   every unit; the install case decides (via webconf / markers).
2. **Pins**: latest `origin/master` (HPlayer2) + latest `origin/2026`
   (Pi-tools) at execution time.
3. **tailscale**: no.
4. **webconf 2026 does support sync mode + channel** (verified):
   `webconf/settings/03-sync.js` exposes SYNC interface (eth0/wlan0), mode
   (disable/slave/master) and channel, implemented by copying
   `/boot/wifi/_disabled/<iface>-sync-{AP,STA}.nmconnection` templates to
   `/boot/wifi/` — exactly the markers `profiles/biennale.py` reads, and
   `network-tools/setnet` loads them into NetworkManager. Same UI and
   convention on both hardwares. Note: 2026 webconf is a **Node.js app**
   (flask version moved to `legacy/`) → N100 needs `nodejs`+`npm` (absent
   today).
5. **x86 "golden state" capture** (Clonezilla): discuss once running.
6. **rtpmidi/raveloxmidi: dropped on BOTH tracks** (N100 and RPi golden) —
   cleanup on N100, and the bench golden card loses it before the 23/07
   capture.
7. **filebrother: not installed, on both tracks.**
8. **webconf (Node) must be verified on the RPi-7.1 golden too** (armv7
   node runtime) — checked in phase 1 on bench player-000.
9. **wint profiles**: the repo gets `wint-hotspot` with a **sanitized
   placeholder psk** (the real fleet psk never enters the public repo — it
   is (re)set device-locally at deploy). `wint-pisync` is retired to a
   `_legacy/` folder. Default-enabled set on every unit, both hardwares:
   **`wint-hotspot` + `eth0-dhcp` only**; all sync/hotspot variants stay
   in `_disabled/` for webconf to activate per install case.
10. **Hostnames stay `mini-01`…`mini-08`** (no rename to `player-NN`).

## Current state (survey #t-019 + phase 0, 2026-07-21)

8× Beelink MINI S (N100) — ledger rows in `extra/biennale26-fleet.md`.
**Phase 0 is DONE**: all 8 aligned on `biennale24@b617c8a` (the 2025
eof/looping fix), reboot-verified (ro rootfs, service active, http2 303).

Common base: Ubuntu 24.04.1 / kernel 6.8.0-41 · `/opt/HPlayer2` (pipenv,
python 3.12.3, czmq/zyre as built submodules) · mpv 0.37 distro ·
Pi-tools `main@6586796` (2024-09-04) in `/opt/Pi-tools`, binaries symlinked
into `/usr/local/bin` · ro rootfs (fstab; `rw`/`ro` helpers) · 16G root
(~5.5G free) + 453G `/data` · profile instance from `/boot/starter.txt` ·
`wint` hotspot 10.0.0.1/24 · avahi ✓ (`mini-0N.local`, IPs are DHCP) ·
internet ✓ · Intel UHD (mpv on DRM, **no /dev/fb0**, no X) · audio HDA
analog + 4× HDMI · x86 RTC ✓ · `/boot/wifi/` exists (2024 layout:
`wint-hotspot` active + `_disabled/`) · **no node/npm**.

Topology luck (all fast-forwards): `b617c8a` ∈ master (158 behind);
Pi-tools `6586796` ∈ `2026`.

⚠ **Runtime `ro` does NOT work on these boxes** (mini-06 pilot, 2026-07-21):
Ubuntu 24.04's systemd 255.4 keeps a rw fd on
`/usr/lib/systemd/systemd-executor`, so `mount -o remount,ro /` always fails
busy; `daemon-reexec` doesn't release it. **End every intervention with a
reboot** (fstab restores ro; doubles as boot-chain check). Also:
`systemctl restart hplayer2@…` reaps the ssh session (benign) — own ssh call.

Green lights for master on x86: python 3.12 ≥ 3.11 ✓ · `rpi-lgpio` arm-gated
✓ · `install_xbian.sh` targets Ubuntu ✓ · audiohub contract-gated (no
`/etc/audiohub.conf` → generic ALSA) ✓ · launcher/kill/unit repo-symlinked ✓
· Pi-tools 2026 has an explicit **x86 install path** (`/boot/pitools.txt`,
`setup/installer.py`).

---

## Phase 0 — align the 8 on the 2025 eof fix — ✅ DONE 2026-07-21

All 8 on `biennale24@b617c8a` (mpv.py md5 `8178c1d2…`), reboot-verified.
Rollback if ever needed: `git checkout master` (268818c).

## Phase 1 — repo-side prep (before touching the fleet again)

1. **BLOCKER — `scripts/color.sh` dies without a framebuffer.** Master's
   launcher runs it under `set -euo pipefail`; no `/dev/fb0` on N100 → the
   embedded python exits 1 → service restart-loop. Patch master: warn +
   exit 0 when the fbdev node is absent (RPi behavior unchanged). Must land
   before any N100 runs master.
2. **Harvest the bench-RPi `/boot/wifi` into Pi-tools `2026`** (Thomas's
   pre-step): player-000 carries a newer, bench-tuned profile set than
   `network-tools/profiles/` (2026-07-20 revisions of `wlan0-sync-AP`
   — hidden, band bg, chan 6, `synclink-1` —, `wlan0-sync-STA`,
   `wlan0-hotspot`, `eth0-*`). Diff bench vs repo, clean (canonical names,
   no machine-specifics), commit to `network-tools/profiles/` on `2026`
   with the layout of decision 9: top level (= enabled at deploy) holds
   `eth0-dhcp` + `wint-hotspot` (placeholder psk), `_disabled/` the sync
   and hotspot variants, `_legacy/` retires `wint-pisync`. N100 deployment
   then flows from the repo (`network-tools/install.sh` does
   `mkdir -p /boot/wifi && cp -r profiles/* /boot/wifi/`), identical for
   both hardwares; the real wint psk is set device-locally after the copy.
3. **webconf (Node) on RPi-7.1 check** (decision 8): on bench player-000,
   confirm the Node webconf service runs (or install/fix it) so both
   hardwares share the same webconf before the N100s adopt it.
4. **rtpmidi off the RPi golden** (decision 6): disable/remove on the
   bench card before the 23/07 capture.
5. Record execution SHAs (master tip + 2026 tip) in the ledger at rollout.

## Phase 2 — pilot one unit (proposal: mini-06)

1. Preflight: `rw` · note `git rev-parse HEAD` both repos · keep a copy of
   `/etc/systemd/system/hplayer2@.service` and of `/boot/wifi/` (2024 set).
2. **Base OS refresh (Thomas: yes, evaluate on pilot)**:
   `apt update && apt upgrade` **within 24.04 LTS** (no release-upgrade).
   Kernel 6.8.0-41 → current 6.8.x; watch the mpv/mesa/VAAPI surface for
   regressions in phase 3. Then the new deps:
   `apt install -y libtool libtool-bin libzmq3-dev nodejs npm`.
3. **uv**: `curl -LsSf https://astral.sh/uv/install.sh | sh` +
   `ln -sf /root/.local/bin/uv /usr/local/bin/uv`.
4. **HPlayer2 → master tip**:
   - `git submodule deinit -f scripts/czmq scripts/zyre` (while still on
     `biennale24`), then `git fetch && git checkout master && git pull`
   - `rm -rf scripts/czmq scripts/zyre .git/modules` (master gitignores
     them; `scripts/bootstrap_native_deps.py` re-clones)
   - `python3 scripts/bootstrap_native_deps.py` then `uv sync`; prove
     `uv run python -c "import czmq, zyre"` (if libs in `/root/.local/lib`
     aren't found: ldconfig drop-in, verify on pilot)
   - unit: `ln -sf /opt/HPlayer2/hplayer2@.service /etc/systemd/system/` +
     `daemon-reload`
   - `/boot/starter.txt`: `hplayer2@biennale24` → `hplayer2@biennale`
     (new settings file `/data/hplayer2-biennale.cfg` appears with
     defaults — recheck volume/mute; media stays `/data/media`)
5. **Pi-tools → 2026 tip**: `git fetch && git checkout 2026`. Then module
   refresh — try the canonical route first: craft `/boot/pitools.txt` for
   N100 (`system=yes, network=yes, web=yes, audioselect=no, xrun=no,
   synczinc=no, bluetooth=no, rtpmidi=no, tailscale=no`) and run the 2026
   `setup.sh` — **if it proves idempotent on an already-provisioned box**;
   fallback = surgical per-module `install.sh`:
   - `network-tools/install.sh` → deploys the harmonized `/boot/wifi`
     template set (phase 1.2): `eth0-dhcp` + `wint-hotspot` enabled,
     variants in `_disabled/` (decision 9); then set the real wint psk
     device-locally.
   - `webconf/install.sh` → Node webconf (`npm install`), replaces the
     flask/legacy one; brings the **SYNC settings page** (decision 4).
   - refresh as needed: starter, rorw, hostrename, extendfs, datesync,
     splash, usbautomount.
   - **skip**: audiohub/audioselect (Pi-only; N100 stays generic ALSA),
     xrun, synczinc, bluetooth-pi, tailscale (decision 3), filebrother
     (decision 7), rtpmidi (decision 6).
6. **SYNC/WALL enablement (decision 1)**: ship every unit with the full
   template set in `/boot/wifi/_disabled/` and **no active sync marker**
   (= SOLO default, current behavior); flipping a unit to WALL
   master/slave on eth0 or wlan0 is a webconf toggle (or a file copy) per
   install case — same gesture as on a RPi.
7. **Cleanup** (after phase-3 validation only):
   - dead Pi-tools symlinks on 2026: `zpinger`, `zmakecert` (modules
     gone), `enforce-ipv4`, `enforce-ping` (moved to `_olides`, deprecated)
     — remove from `/usr/local/bin` + their `/boot/starter.txt` lines
   - legacy flask webconf: venv `webconf-MRnSNi8u` + its starter entry
     (replaced by Node webconf)
   - HPlayer2 pipenv venv `HPlayer2-t6Bmc4Im` + stray `-x-v5uFv0`, then
     `apt-get remove pipenv` (nothing uses it once both webconf and
     hplayer2 are off it) + `apt autoremove`
   - old czmq/zyre submodule leftovers (step 4 already removed them)
   - **rtpmidi/raveloxmidi (decision 6)**: stop+disable `rtpmidid`,
     remove the `rtpmidi`/`raveloxmidi` symlinks and their starter.txt
     lines.
8. Reboot (restores ro) ×2.

## Phase 3 — pilot verification checklist

- Boots ro, starter launches `hplayer2@biennale`, **no restart loop**
  (color.sh patched), journal clean after apt upgrade (kernel/mesa).
- http2 :80 → 303 `/full`, UI loads, upload lands in `/data/var/tmp`.
- Media plays from `/data/media`; **gapless loop across EOF**; images 15s.
- **Play/loop matrix (Thomas, 2026-07-21)** — all four cells must
  auto-play on boot and auto-loop indefinitely:
  | | single media | multi-media playlist |
  |---|---|---|
  | **SOLO** | auto-play + loop | auto-play + sequential loop |
  | **SYNC/WALL** | master-driven synced play + loop | master-driven synced playlist + loop |
- **audiohub contract (Thomas, 2026-07-21)**: on the RPi side of the
  mixed test, confirm the new audiohub is detected (`/etc/audiohub.conf`
  + `/data` override) and the **latency compensation is calculated as
  designed**; on the N100 (no audiohub.conf) confirm HPlayer2 stays on
  generic ALSA with no hub logic engaged.
- `uv run python -c "import czmq, zyre"` ✓; zeroconf announce visible.
- webconf (Node) reachable; **SYNC page flips markers correctly** (toggle
  slave → verify `/boot/wifi/eth0-sync-STA.nmconnection` + setnet loads
  it → toggle back to disable/SOLO).
- **Mixed-hardware WALL test (the parity goal)**: bench player-000 (RPi,
  golden candidate) + pilot N100, same `biennale` profile, one master one
  slave on the sync markers — zyre lock + wallclock chase verified across
  architectures, then both returned to SOLO.
- wint hotspot up (10.0.0.1, dnsmasq leases OK) after profile refresh.
- Audio out (analog/HDMI) unchanged; mpv still picks DRM video after the
  mesa/kernel upgrade.
- Pi-tools helpers still good: `rw`, fake-clock, hostrename, starter.
- Reboot ×2: clock sane, service returns, rootfs ro.
- Optional 24h soak: journal free of mpv/watchdog storms.

## Phase 4 — fleet rollout

Same steps on the remaining 7, **mini-07 last** (living 2024 reference
until the end). Update the ledger rows per machine (`now=<master tip SHA>`,
`instance=hplayer2@biennale`, note the Pi-tools SHA). Rollback stays cheap
while cleanup (2.7) hasn't run on a unit: old venvs still present +
`git checkout b617c8a` + restore unit file + starter.txt line + old
`/boot/wifi` backup.

## Phase 5 — bookkeeping

Ledger commits (`Refs-37: biennale-lyon-2026#t-020`), `/brain-out` the
x86-convergence knowledge, revisit the Clonezilla capture question
(decision 5) once the fleet runs.

---

## Phase 1 outcomes (2026-07-21)

- 1.1 ✅ `color.sh` fbdev-absent guard — HPlayer2 `master@17cdb84`.
- 1.2 ✅ bench profiles harvested — Pi-tools `2026@d555b0b` (layout per
  decision 9, psk sanitized).
- 1.3 ✅ **webconf verified on RPi-7.1** (decision 8) — found
  **crash-looping** (`Cannot find module 'bonjour-service'`: the golden
  card was hand-provisioned without the module's `npm install`); fixed by
  running `npm install` in `/opt/Pi-tools/webconf` → HTTP 200 on :4038,
  node 18.20.8 armv7. Card restored (service stopped as found, ro). ⚠ its
  starter.txt still reads `# webconf ## Not working properly` — stale,
  refresh before the golden capture.
- 1.4 ✅ rtpmidi on the RPi golden: **already absent** — decision 6 is a
  no-op there; only the N100s run `rtpmidid` (cleanup in phase 2.7).

## Installer review (Thomas's ask, 2026-07-21)

**x86/Ubuntu Server fresh image → this golden state: YES, near-complete.**
`setup/bootstrap.py` consolidates the old per-platform bootstrap scripts
(ssh root login, NM+dnsmasq with netplan handover, ipv6 off, `net.ifnames=0`
grub, `iwlwifi→wint` udev rename — matches the Beelink chip, node via
`n lts`, uv, mosquitto/avahi/haveged) and `rorw/install.sh` regenerates the
exact ro-fstab scheme, x86-aware (sda3/nvme detection — matches the Beelink
sda1/2/3 layout) **including two fixes the 2024 N100 images lack**: the
`/root/.cache → /data/var/cache` bind (uv cache would otherwise sit on the
ro root) and swap removal. → **Re-run `rorw/install.sh` on the N100s in
phase 2.5 to normalize fstab.** Gaps to document, not blockers:
1. The installer does NOT partition — the root+`/data` split must pre-exist
   (fresh install: Ubuntu autoinstall layout; recommend committing an
   autoinstall/cloud-init reference to Pi-tools).
2. HPlayer2 is out of installer scope — provisioning is two-step
   (Pi-tools `setup.sh`, then HPlayer2 `install.sh` + bootstrap_native_deps
   + `uv sync`).
3. `--yes` treats `ask`-modules as *no* → golden builds need a
   `pitools.txt`; recommend committing canonical fleet configs (e.g.
   `pitools-biennale-n100.txt`).
4. `pitools.example.txt` drift: still says `audioselect` where the module
   is now `audiohub`.

**RPi OS fresh image → RPi-7.1 golden: NOT equivalent (by design).** The
installer codifies the **KMS/new-stack** flavor (config.txt `vc4-kms-v3d`,
distro node ceiling 18 on armv7, no custom mpv); the 7.1 golden is the
AnnaTV **legacy-stack** capture (mpv 0.33 + ffmpeg 4.4 mmal/omx in
/usr/local, kernel 6.18 rpi-update pin). On a 3B+ mmal is the only
accelerated path → **the golden image remains the sole reflash source for
the RPi fleet**; the installer is the source of truth for x86 (and future
KMS-era Pi parks). Worth stating in the Pi-tools README.

---

*v3 (2026-07-21): all open points settled by Thomas (decisions 6–10) —
plan confirmed, execution green-lit.*
