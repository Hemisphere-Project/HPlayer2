from core.engine.hplayer import HPlayer2

import os

# DEV profile: exercise the radar + schedule interfaces over a pty pair (no hardware).
#
#   socat -d pty,raw,echo=0,link=/tmp/hp2-radar-host pty,raw,echo=0,link=/tmp/hp2-radar-dev &
#   python3 extra/test/radar_mockdevice.py /tmp/hp2-radar-dev     (another terminal)
#   ./hplayer2 radartest
#
# env overrides: RADAR_PORT (default /tmp/hp2-radar-host), RADAR_MEDIA (default /tmp/hp2-radar-media)

port = os.environ.get('RADAR_PORT', '/tmp/hp2-radar-host')
media = os.environ.get('RADAR_MEDIA', '/tmp/hp2-radar-media')
os.makedirs(media, exist_ok=True)

hplayer = HPlayer2([media])

player = hplayer.addPlayer('mpv', 'player')

hplayer.addInterface('http2', 80 if hplayer.isRPi() else 8080,
                     {'playlist': False, 'loop': False, 'mute': True})
radar = hplayer.addInterface('radar', port)     # '/'-prefixed filter -> literal device (the pty)
schedule = hplayer.addInterface('schedule', 5)  # short tick so edges show up fast in a test

# Build playlist from the media folder
@hplayer.files.on('file-changed')
@hplayer.files.on('filelist-updated')
def build_list(ev=None, *args):
    hplayer.playlist.load(hplayer.files.currentList())
build_list()

# TRIGGER: play on entry, but only inside the schedule window and only if idle (play-out)
@hplayer.on('radar.enter')
def onEnter(ev, *args):
    if schedule.isOpen() and not player.isPlaying():
        hplayer.playlist.play()

@hplayer.on('schedule.close')
def onClose(ev, *args):
    player.stop()

# Persist radar + schedule tunables edited from the http2 web UI (interfaces read them live)
for key in ('radar-range', 'radar-width', 'radar-enter-ms', 'radar-leave-ms',
            'schedule-enable', 'schedule-open', 'schedule-close'):
    hplayer.on('http2.' + key)(lambda ev, *a, k=key: hplayer.settings.set(k, a[0]))

@hplayer.on('radar.*')
@hplayer.on('schedule.*')
def http2_logs(ev, *args):
    hplayer.interface('http2').send('logs', [ev] + list(args))

# RUN
hplayer.run()
