from core.engine.hplayer import HPlayer2

import os

# DEV profile: exercise the teleco2 interface over a pty pair (no CoreS3 needed)
#
#   socat -d pty,raw,echo=0,link=/tmp/hp2r-host pty,raw,echo=0,link=/tmp/hp2r-dev &
#   python3 extra/test/teleco2_mockdevice.py /tmp/hp2r-dev     (in another terminal)
#   ./hplayer2 teleco2test
#
# env overrides: TELECO2_PORT (default /tmp/hp2r-host), TELECO2_MEDIA (default /tmp/hp2r-media)

port = os.environ.get('TELECO2_PORT', '/tmp/hp2r-host')
media = os.environ.get('TELECO2_MEDIA', '/tmp/hp2r-media')
os.makedirs(media, exist_ok=True)

hplayer = HPlayer2([media])

player = hplayer.addPlayer('mpv', 'mpv')

teleco2 = hplayer.addInterface('teleco2', False, 'wlan0', port)

# Build playlist from media folder
@hplayer.files.on('file-changed')
@hplayer.files.on('filelist-updated')
def build_list(ev=None, *args):
    hplayer.playlist.load(hplayer.files.currentList())
build_list()

# Parc-mode wiring (anna.py does broadcast() here; we just act locally to close the loop)
@hplayer.on('teleco2.remote-prev')
def rprev(ev, *args):
    hplayer.playlist.prev()

@hplayer.on('teleco2.remote-next')
def rnext(ev, *args):
    hplayer.playlist.next()

@hplayer.on('teleco2.remote-stop')
def rstop(ev, *args):
    teleco2.emit('stop')

@hplayer.on('teleco2.remote-playindex')
def rplayindex(ev, *args):
    hplayer.playlist.playindex(int(args[0]))

@hplayer.on('teleco2.remote-playpause')
def rplaypause(ev, *args):
    if player.isPaused():
        teleco2.emit('resume')
    elif player.isPlaying():
        teleco2.emit('pause')
    else:
        teleco2.emit('play')

@hplayer.on('teleco2.remote-volup')
def rvolup(ev, *args):
    teleco2.emit('volinc')

@hplayer.on('teleco2.remote-voldown')
def rvoldown(ev, *args):
    teleco2.emit('voldec')


# RUN
hplayer.run()
