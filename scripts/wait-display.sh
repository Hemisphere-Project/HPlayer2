#!/bin/bash
# Bounded wait for a connected DRM connector before starting the player.
#
# On fast silent boots the box can win the race against the display's HDMI
# link training: mpv then fails its one vo init and idles BLACK until a
# manual restart (mini-01, 2026-07-22 — the N100s boot faster than some
# screens wake). Venue reality is player and screen on the same power
# switch, so the race is systemic, not a bench quirk.
#
# Semantics: wait up to 15s for ANY connector to report connected, then
# start regardless — a genuinely headless box keeps today's behavior (no
# playback until a screen + restart), and boxes without DRM connectors
# (RPi legacy/mmal stack: firmware owns the display, no race) skip the
# wait entirely.

shopt -s nullglob
STATUSES=(/sys/class/drm/card*-*/status)
[ ${#STATUSES[@]} -eq 0 ] && exit 0     # no DRM connectors (legacy Pi): no-op

for _ in $(seq 1 15); do
    if grep -q "^connected" "${STATUSES[@]}" 2>/dev/null; then
        exit 0
    fi
    sleep 1
done
echo "wait-display: no connected DRM connector after 15s — starting anyway (headless?)"
exit 0
