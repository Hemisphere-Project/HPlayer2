from core.engine.hplayer import HPlayer2
from core.engine import network
import time

# EXTRA TMP UPLOAD
import tempfile
tempfile.tempdir = '/data/var/tmp'


# INIT HPLAYER
hplayer = HPlayer2('/data/media', '/data/hplayer2-gadagne21.cfg')


# PLAYER
player = hplayer.addPlayer('mpv', 'player')
player.doLog['events'] = True
# player.doLog['cmds'] = True

# SAMPLER
# sampler = hplayer.addSampler('mpv', 'sampler', 4)


# Interfaces
hplayer.addInterface('http', 8080)
hplayer.addInterface('http2', 8000)
if hplayer.isRPi():
    hplayer.addInterface('gpio', [26,19,13,6], 310)
if "-sync" in network.get_hostname():
	hplayer.addInterface('zyre', 'wlan0')



# PLAY action
def doPlay(media):
	if "-sync" in network.get_hostname():
		if "-master" in network.get_hostname():
			hplayer.getInterface('zyre').node.broadcast('/play', list(media), 200)
			print('doPLay: master.. broadcast')
		else:
			print('doPLay: slave.. do nothing')
	else:
		hplayer.playlist.play(media)



# DEFAULT File
@hplayer.on('player.ready')
@hplayer.on('playlist.end')
def play0(ev, *args):
    doPlay("0_*.*")


# HTTP + GPIO events
@hplayer.on('http.push1')
@hplayer.on('gpio.26-on')
def play1(ev, *args):
    doPlay("1_*.*")

@hplayer.on('http.push2')
@hplayer.on('gpio.19-on')
def play1(ev, *args):
    doPlay("2_*.*")

@hplayer.on('http.push3')
@hplayer.on('gpio.13-on')
def play1(ev, *args):
    doPlay("3_*.*")

@hplayer.on('http.push4')
@hplayer.on('gpio.6-on')
def play1(ev, *args):
    doPlay("4_*.*")



# SETTINGS (pre-start)
player.imagetime(15)


# RUN
hplayer.run()
