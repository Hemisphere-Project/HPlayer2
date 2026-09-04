import json
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
# Surface (LED transform), first found:     /data/sync/solo/<hostname>/surface.json
#                                           /data/sync/<SHOW>/surface.json   (keyed by hostname)
#   {
#     "width": 256, "height": 512,        # LED-native block, in output pixels (0 = source size)
#     "rotate": 0,                         # degrees, any angle
#     "halfheight": true,                  # even-line LED panels: squash the block to half height
#     "fit": "cover",                      # cover | contain | stretch
#     "align": "center",                   # center | left  (horizontal crop / content alignment)
#     "source_offset_x": 0, "source_offset_y": 0,
#     "output_x": 0, "output_y": 0,        # where the block lands on the HDMI output
#     "correction": {"brightness": 70}     # any correction_* param of 02-correction.glsl
#   }
#   No surface.json → the shader is bypassed (plain full-screen mpv).
#   The file is re-read whenever the synced tree changes, so a fix lands live.

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
hplayer.addInterface('http2', 8080)                    # web UI + media management
hplayer.addInterface('http', 8081)                     # plain GET API (/stop, /status …)
hplayer.addInterface('regie', 9111, projectfolder)     # RPi-Regie page + sequence dispatch


#
# SURFACE (LED transform) → shader params
#
FIT = {'cover': 0.0, 'contain': 1.0, 'stretch': 2.0}

def load_surface():
    """first found: the box's solo surface.json, else the show-wide one keyed by hostname"""
    solo = os.path.join(devicefolder, 'surface.json')
    show = os.path.join(projectfolder, 'surface.json')
    for path in (solo, show):
        if not os.path.isfile(path):
            continue
        try:
            with open(path) as fd:
                data = json.load(fd)
        except (OSError, ValueError) as e:
            hplayer.log('surface: cannot read', path, e)
            continue
        if path == show:
            data = data.get(devicename)
            if data is None:
                continue
        return data, path
    return None, None


def apply_surface(ev=None, *args):
    conf, path = load_surface()
    if not conf:
        video.shaderParam('scaler_enable', 0.0)
        hplayer.log('surface: none → shader bypassed')
        return
    params = {
        'scaler_enable':          1.0,
        'scaler_width':           float(conf.get('width', 0)),
        'scaler_height':          float(conf.get('height', 0)),
        'scaler_rotate':          float(conf.get('rotate', 0)),
        'scaler_halfheight':      1.0 if conf.get('halfheight') else 0.0,
        'scaler_fit':             FIT.get(str(conf.get('fit', 'cover')).lower(), 0.0),
        'scaler_sourcealign':     0.0 if str(conf.get('align', '')).lower() == 'left' else 1.0,
        'scaler_sourceoffset_x':  float(conf.get('source_offset_x', 0)),
        'scaler_sourceoffset_y':  float(conf.get('source_offset_y', 0)),
        'scaler_output_x':        float(conf.get('output_x', 0)),
        'scaler_output_y':        float(conf.get('output_y', 0)),
    }
    for key, value in (conf.get('correction') or {}).items():
        params['correction_' + key] = float(value)
    video.shaderParam(params)
    hplayer.log('surface:', path, conf)


@hplayer.on('app-run')
@hplayer.on('files.filelist-updated')
def onTreeChange(ev, *args):
    apply_surface()


# DEFAULTS
@hplayer.on('app-run')
def init(ev, *args):
    hplayer.settings.set('volume', 100)


# RUN
hplayer.run()
