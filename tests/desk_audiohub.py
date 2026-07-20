"""
Audiohub desk test: real-pipeline validation of the USB mirror side-car with
zero audio hardware — snd-aloop stands in for the graph's loopback slave and
the ALSA 'null' device stands in for the USB card.

- test 1: a raw alsaloop forwarder (hw:Loopback,1,0 -> null) holds while the
  playback side is fed, exactly the topology mpv drives on the 7.1 image.
- test 2: the AudiohubInterface supervision loop spawns a REAL alsaloop for a
  faked card scan, reports 'active', respawns it after a kill, and tears down.

Requirements: alsa-utils (alsaloop, aplay) + the snd-aloop module loaded (or
loadable: run once as root, or `sudo modprobe snd-aloop`). Skips cleanly when
the box can't provide them.

    python3 tests/desk_audiohub.py          # ~20 s
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
                        '-r', '48000', '-f', 'S16_LE', '-c', '2',
                        '-t', '8000', '-S', 'auto'],
                       stderr=subprocess.PIPE, universal_newlines=True)
feed = subprocess.Popen(['aplay', '-q', '-D', 'hw:Loopback,0,0',
                         '-c', '2', '-f', 'S16_LE', '-r', '48000',
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


print('== test 2: AudiohubInterface supervision with a real alsaloop')


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


class DeskHub(AudiohubInterface):
    def _checkGraph(self):
        return True                        # pretend the graph is deployed

    def _scanUsb(self):
        return {'id': 'Desk', 'index': 99, 'channels': 2}


audiohub.pick_usb_egress = lambda card_id, channels: 'null'   # "USB card" = null sink

hub = DeskHub(StubHPlayer())
hub.start()
try:
    deadline = time.time() + 5
    while time.time() < deadline and hub._usbState() != 'active':
        time.sleep(0.2)
    if hub._usbState() != 'active':
        fail('mirror never became active (state=%s)' % hub._usbState())
    print('   ok: mirror active')

    hub._proc.kill()
    deadline = time.time() + 10
    while time.time() < deadline:
        time.sleep(0.2)
        if hub._usbState() == 'active' and hub._proc and hub._proc.poll() is None \
           and hub._deaths >= 1:
            break
    else:
        fail('forwarder was not respawned after kill (state=%s deaths=%d)'
             % (hub._usbState(), hub._deaths))
    print('   ok: forwarder respawned after kill (deaths=%d)' % hub._deaths)
finally:
    hub.quit()

if hub._proc is not None:
    fail('quit left a forwarder behind')
print('   ok: clean teardown')

print('PASS')
