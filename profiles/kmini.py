import os

from core.engine import network
from core.engine.hplayer import HPlayer2

# KMINI — KXKM mini-PC show player (Intel N150 minis, Ubuntu 25.10 + Pi-tools 2026)
#
# An ordinary Zyre peer of the RPi-Regie / sacvp fleet: same synced show folder,
# same project.json, same cues, same peer-name = hostname (kmini-001 …). What
# differs from a Pi:
#   - mpv renders on the DRM console (no X); LED transforms come from the GLSL
#     scaler shader, configured PER BOX in surface.json (see below)
#   - NDI: a `.ndi` media (first line = source name) or `ndi://<source>` plays the
#     HNdi loopback device through the same mpv (core/players/mpv.py)
#   - none of the Pi-only hardware (LPD8 sampler pad, teleco, k32 btserial, CASA mqtt)
#
# Media tree (synced, same as the Pis):    /data/sync/<SHOW>/<scene>/<media>
# Per-box folder (solo media, overrides):   /data/sync/solo/<hostname>/
# Surface (LED / output transform):         a persisted SETTING (`surface`, see
#   core/engine/settings.py SURFACE_DEFAULTS, disabled by default) edited live in the
#   http2 page's "Surface (LED)" card (shown only where the player has the GLSL scaler,
#   i.e. mpv on x86) and saved with the other settings in the profile's .cfg.
#   Enabled = the picture is anchored TOP-LEFT (use screen-aspect content, e.g. 1080p).
#   From scripts: GET http://<box>:8081/surface/{"width":256,"height":512,"halfheight":true}

SHOW = 'sacvp'

profilename = os.path.basename(__file__).split('.')[0]
projectfolder = os.path.join('/data/sync', SHOW)

devicename = network.get_hostname()
devicefolder = os.path.join('/data/sync/solo', devicename)

base_path = ['/data/usb', projectfolder, devicefolder]


# INIT HPLAYER
hplayer = HPlayer2(base_path, "/data/hplayer2-" + profilename + ".cfg")


# PLAYER: one mpv, HDMI out, still images held until the next cue
video = hplayer.addPlayer('mpv', 'video')
video.imagetime(0)


# NETWORK: Zyre on the wired link when it carries an address, else the WiFi.
# (a mini at the show is on Ethernet; on a bench or a WiFi-only venue it is on wint)
def _iface_with_ip(candidates):
    for iface in candidates:
        if network.has_interface(iface) and network.get_ip(iface) != '127.0.0.1':
            return iface
    return None

ZYRE_IFACE = _iface_with_ip(['eth0', 'enp1s0', 'wint', 'wlan0'])
hplayer.log('zyre interface:', ZYRE_IFACE or '(default)')
if ZYRE_IFACE:
    hplayer.addInterface('zyre', ZYRE_IFACE)
else:
    hplayer.addInterface('zyre')


# INTERFACES
hplayer.addInterface('http2', 8080)                    # web UI + media management (+ Surface card, mpv/x86)
hplayer.addInterface('http', 8081)                     # plain GET API (/stop, /status …)
hplayer.addInterface('regie', 9111, projectfolder)     # RPi-Regie page + sequence dispatch


# DEFAULTS
@hplayer.on('app-run')
def init(ev, *args):
    hplayer.settings.set('volume', 100)


# RUN
hplayer.run()
