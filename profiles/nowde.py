from core.engine.hplayer import HPlayer2
from core.engine import network
from platformdirs import user_data_dir
from termcolor import colored
import os
import time
import re
import math

# Get platform-specific config directory
DATADIR = user_data_dir("HPlayer2", "Hemisphere")
os.makedirs(DATADIR, exist_ok=True)

# EXTRA TMP UPLOAD
import tempfile
tempfile.tempdir = DATADIR + '/tmp'
os.makedirs(tempfile.tempdir, exist_ok=True)

# MEDIA PATH
LOCALMEDIA = DATADIR + '/media'
os.makedirs(LOCALMEDIA, exist_ok=True)
mediaPath = [LOCALMEDIA]

# INIT HPLAYER
hplayer = HPlayer2(mediaPath, DATADIR+'/hplayer2.cfg')

# PLAYER
player = hplayer.addPlayer('mpv', 'player')
player.imagetime(15)

player.doLog['events'] = True
player.doLog['cmds'] = True


# Interfaces
# hplayer.addInterface('http', 8081)
hplayer.addInterface('http2', 8080, {'playlist': False, 'loop': False, 'mute': True})
hplayer.addInterface('mtc', re.compile("rtpmidid:(?!Nowde)+") )
# hplayer.addInterface('serial', '^M5', 10)


# PLAY action
debounceLastTime = 0
debounceLastMedia = ""

def doPlay(media, debounce=0):
    	
	# DEBOUNCE media
	global debounceLastTime, debounceLastMedia
	now = int(round(time.time() * 1000))
	if debounce > 0 and debounceLastMedia == media and (now - debounceLastTime) < debounce:
		return
	debounceLastTime = now
	debounceLastMedia = media

	hplayer.playlist.play(media)


# DEFAULT File
# @hplayer.on('app-run')
# @hplayer.on('files.filelist-updated')
# @hplayer.on('playlist.end')
# def play0(ev, *args):
# 	doPlay("[^1-9_]*.*")
# 	hplayer.settings.set('loop', 0)

#
# MTC
#

lastSpeed = 1.0
lastPos = -1
didJump = False
jumpFix = 500       # compensate the latency of jump (300ms for RockPro64 on timecode jump I.E. looping)
kickStart = 0

@hplayer.on('mtc.qf')
@hplayer.on('osc.time')
def f(ev, *args):
	global lastSpeed, lastPos, didJump, jumpFix, kickStart

	# print(args[0], ev)
	# if ev == 'mtc.qf':
	# 	print('converting')
	# 	args[0] = args[0].float
	# 	print(args[0])

	doLog = True

	pos = player.position()

	# Resume if paused
	if player.isPaused():
		player.resume()

	# Player has been launched, wait for it to start
	if kickStart > 0:
		kickStart -= 1
		# print("kickStart", kickStart)

	# Play if stopped
	elif not player.isPlaying():

		if kickStart < 0:
			kickStart += 1
		else:
			hplayer.playlist.playindex(0)
			pos = 0
			kickStart = 20
	else:
		kickStart = -3

	# Check if player time is actually ellapsing
	if pos == lastPos or not player.isPlaying():
		if doLog and kickStart == 0:
			print(str(args[0]), end="\t")
			print("no news from player.. dropping timecode tracking on this frame")
		return
	lastPos = pos

	if ev == 'mtc.qf':
		clock = round(args[0].float, 2)
	else:
		clock = round(float(args[0]), 2)
	diff = clock-pos

	speed = 1.0

	# framebuffer corrector
	#fix = 0.04    # compensate mtc latency from clock to tc tracker (typically 1 frame on Ubuntu x64 using Alsa Midi:Thru)
	fix = 0


	#jump
	if diff > 10 or diff < -2:
		player.seekTo(clock*1000+jumpFix)
		didJump = True
		print(str(args[0]), end="\t")
		print("timedelay=" + colored(round(diff,2),"red"), end="\t")
		print("JumpFix", jumpFix)

	else:   

		# Jump correction
		if didJump:
			didJump = False
			# Correcting JumpFix is dangerous: might diverge on different jump position / media quality / ...
			# if abs(diff+fix) > 0.01:
			#     jumpFix += min( max(-300, (diff+fix)*1000), 300)
			#     print("corrected JumpFix", jumpFix)

		# accel
		if (diff+fix) > 0.043 or (lastSpeed>1 and (diff+fix) > 0) :
			speed = round( 1+ (diff+fix)*1.5, 2)
			speed = min(speed, 4.2)

		# decel
		elif (diff+fix) < -0.043 or (lastSpeed<1 and (diff+fix) < 0):
			speed = round( 1+ min(-0.03, (diff+fix)*1.5 ), 2)
			speed = max(speed, 0.1)

	player.speed(speed)
	lastSpeed = speed

	# LOG
	if doLog:
		if speed != 1.0:
			color1 = 'green'
			if abs(diff+fix) > 0.08: color1 = 'red'
			elif abs(diff+fix) > 0.04: color1 = 'yellow'

			color2 = 'white'
			if speed > 1: color2 = 'magenta'
			elif speed < 1: color2 = 'cyan'


			framedelta = math.trunc(diff*1000/30)
			color3 = 'green'
			if abs(framedelta) > 1: color3 = 'red'
			elif abs(framedelta) > 0: color3 = 'yellow'

			# print(str(args[0]), end="\t")
			# print(str(clock), end="\t")
			# print(str(pos), end="\t")
			print("timedelay=" + colored(round(diff,2),color1), end="\t")
			print("framedelta=" + colored(framedelta,color3), end="\t")
			print("speed=" + colored(speed, color2) )
		
  
# HTTP2 Logs
@hplayer.on('player.*')
@hplayer.on('sampler.*')
@hplayer.on('gpio.*')
@hplayer.on('serial.*')
def http2_logs(ev, *args):
	if ev.startswith('gpio') and ev.find('-') == -1: return 
	if len(args) and args[0] == 'time': return
	hplayer.interface('http2').send('logs', [ev]+list(args))

# RUN
hplayer.run()
