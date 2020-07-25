from core.engine.hplayer import HPlayer2
from core.engine import network
import time

# EXTRA TMP UPLOAD
import tempfile
tempfile.tempdir = '/data/var/tmp'


# INIT HPLAYER
hplayer = HPlayer2('/data/media', '/data/hplayer2-puzzle.cfg')

# PLAYER
player = hplayer.addPlayer('mpv', 'player')

# SAMPLER
sampler = hplayer.addSampler('mpv', 'sampler', 4)


# Interfaces
hplayer.addInterface('http2', 8000)
hplayer.addInterface('serial', "^CP2102")


# DEFAULT File
@hplayer.on('player.ready')
@hplayer.on('playlist.end')
def play0(ev, *args):
    hplayer.playlist.play("0_*.*")

# SERIAL events
@hplayer.on('serial.playsample')
def playsample(ev, *args):
    sampler.play( hplayer.files.listFiles(args[0]+"_*.*")[0] )

@hplayer.on('serial.stopsample')
def playsample(ev, *args):
    sampler.stop( hplayer.files.listFiles(args[0]+"_*.*")[0] )

# RUN
hplayer.run()
