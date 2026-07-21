"""
Audiohub desk test: real-pipeline validation of the output forwarders with
zero audio hardware — snd-aloop stands in for the hub's loopback and the ALSA
'null' device stands in for every physical sink.

- test 1: a raw alsaloop forwarder (hw:Loopback,1,0 -> null) holds while the
  playback side is fed, exactly the topology mpv drives on the 7.1 image.
- test 2: the AudiohubInterface supervision loop spawns REAL alsaloops for
  jack/hdmi (and a faked USB card scan), reports 'active', respawns one after
  a kill, and tears down clean.

Requirements: alsa-utils (alsaloop, aplay) + the snd-aloop module loaded (or
loadable: run once as root, or `sudo modprobe snd-aloop`). Skips cleanly when
the box can't provide them.

    python3 tests/desk_audiohub.py          # ~25 s
"""
import os
import shutil
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import core.interfaces.audiohub as audiohub
from core.interfaces.audiohub import AudiohubInterface, parse_cards


def skip(reason):
    print('SKIP:', reason)
    sys.exit(0)


def fail(reason):
    print('FAIL:', reason)
    sys.exit(1)


def have_loopback():
    try:
        with open('/proc/asound/cards') as fd:
            return any(c['id'] == 'Loopback' for c in parse_cards(fd.read()))
    except OSError:
        return False


# --- preconditions ----------------------------------------------------------

if not sys.platform.startswith('linux'):
    skip('linux only')
if not shutil.which('alsaloop') or not shutil.which('aplay'):
    skip('alsa-utils (alsaloop, aplay) not installed')
if not have_loopback():
    subprocess.run(['modprobe', 'snd-aloop'], check=False,
                   stderr=subprocess.DEVNULL)
    if not have_loopback():
        skip('snd-aloop not loaded (sudo modprobe snd-aloop)')

print('== test 1: raw forwarder pipeline (hw:Loopback,1,0 -> null)')

fwd = subprocess.Popen(['alsaloop', '-C', 'hw:Loopback,1,0', '-P', 'null',
                        '-r', '48000', '-f', 'S16_LE', '-c', '8',
                        '-t', '8000', '-S', 'auto'],
                       stderr=subprocess.PIPE, universal_newlines=True)
feed = subprocess.Popen(['aplay', '-q', '-D', 'hw:Loopback,0,0',
                         '-c', '8', '-f', 'S16_LE', '-r', '48000',
                         '-d', '5', '/dev/zero'])
time.sleep(5)
if fwd.poll() is not None:
    err = fwd.stderr.read()
    feed.terminate()
    fail('alsaloop died during feed: ' + err.strip()[:400])
feed.wait()
fwd.terminate()
fwd.wait()
print('   ok: forwarder held for 5s of playback')


print('== test 2: AudiohubInterface supervision with real alsaloops')


class StubSettings:
    def __init__(self):
        self._settings = {}

    def get(self, key):
        return self._settings.get(key)


class StubHPlayer:
    settings = StubSettings()

    def autoBind(self, module):
        return None

    def interface(self, name):
        return None

    def players(self):
        return []


class DeskHub(AudiohubInterface):
    def __init__(self, hplayer):
        super().__init__(hplayer)
        # no jackout/hdmiout/aloopcap PCMs on a dev box: every sink is 'null'
        # and the capture side reads the loopback directly (single reader per
        # substream is fine here — dsnoop sharing is the image's concern)
        self._fwd['jack'].device = 'null'
        self._fwd['hdmi'].device = 'null'

    def _checkGraph(self):
        return True                        # pretend the graph is deployed

    def _scanUsb(self):
        return {'id': 'Desk', 'index': 99, 'channels': 2}


audiohub.pick_usb_egress = lambda card_id, channels: 'null'   # "USB card" = null

_orig_cmd = audiohub.build_alsaloop_cmd
_capidx = 0


def _desk_cmd(device, tlatency_us, chrt=None, alsaloop='alsaloop', capture=None):
    # one loopback substream per forwarder (no dsnoop on the desk)
    global _capidx
    cmd = _orig_cmd(device, tlatency_us, chrt=chrt, alsaloop=alsaloop,
                    capture='hw:Loopback,1,%d' % (_capidx % 8))
    _capidx += 1
    return cmd


audiohub.build_alsaloop_cmd = _desk_cmd

hub = DeskHub(StubHPlayer())
hub.start()
try:
    deadline = time.time() + 6
    while time.time() < deadline and not (
            hub._fwd['jack'].state() == 'active'
            and hub._fwd['hdmi'].state() == 'active'
            and hub._usbState() == 'active'):
        time.sleep(0.2)
    states = {n: f.state() for n, f in hub._fwd.items()}
    if not all(s == 'active' for s in states.values()):
        fail('forwarders never all active: %s' % states)
    print('   ok: jack/hdmi/usb forwarders active')

    hub._fwd['jack'].proc.kill()
    deadline = time.time() + 10
    while time.time() < deadline:
        time.sleep(0.2)
        if hub._fwd['jack'].alive() and hub._fwd['jack'].deaths >= 1:
            break
    else:
        fail('jack forwarder was not respawned after kill (deaths=%d)'
             % hub._fwd['jack'].deaths)
    if hub._fwd['hdmi'].deaths or (hub._fwd['usb'].deaths if 'usb' in hub._fwd else 0):
        fail('unrelated forwarders died with the jack one')
    print('   ok: jack respawned after kill, hdmi/usb untouched')
finally:
    hub.quit()

if any(f.proc is not None for f in hub._fwd.values()):
    fail('quit left a forwarder behind')
print('   ok: clean teardown')

print('PASS')
