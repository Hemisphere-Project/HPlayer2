from core.engine.hplayer import HPlayer2
from core.engine import network
import os, sys, types, platform

# DIRECTORY / FILE
profilename = os.path.basename(__file__).split('.')[0]
base_path = ['/data/sync/', '/data/usb']

hplayer = HPlayer2(base_path)

# PLAYERS
player 	= hplayer.addPlayer('mpv','mpv')

# Interfaces
hplayer.addInterface('mtc', "Midi Through:Midi Through Port-0 14:0")

# No Loop, neither playlist
@hplayer.on('mpv.ready')
def f(ev, *args):
	hplayer.settings.set('loop', -1)


@hplayer.on('mpv.ready')
def f(ev, *args):
	hplayer.playlist.play('*')
	# player.pause()

lastPos = -1

@hplayer.on('mtc.qf')
def f(ev, *args):
	pos = player.position()

	# Check if player time is actually ellapsing
	global lastPos
	if pos == lastPos or not player.isPlaying():
		# print("no news from player.. timecode tracker standing by")
		return
	lastPos = pos

	clock = round(args[0].float, 2)
	diff = clock-pos
	speed = 1.0

	# corrector
	fix = 0.04	# compensate mtc latency from clock to tc tracker (typically 1 frame on Ubuntu x64 using Alsa Midi:Thru)

	#jump
	if abs(diff) > 1.0:
    		player.seekTo(clock*1000)

	# accel / decel
	elif abs(diff+fix) > 0.04:
		speed = round( 1+diff+fix, 2)
		speed = max(min(speed, 100.0), 0.1)

	print(args[0], clock, pos, "delay=", round(diff,2), speed)
    
	player.speed(speed)
	


# RUN
hplayer.run()                               						# TODO: non blocking
