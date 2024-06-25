from core.engine.hplayer import HPlayer2
from core.engine import network
import time
import random

# EXTRA TMP UPLOAD
import tempfile
tempfile.tempdir = '/data/var/tmp'

# MEDIA PATH
mediaPath = ['/data/media', '/data/usb']

# INIT HPLAYER
hplayer = HPlayer2(mediaPath, '/data/hplayer2-trames.cfg')


# PLAYER
player = hplayer.addPlayer('mpv', 'player0')

# SAMPLER
sampler = hplayer.addSampler('mpv', 'sampler', 3)

# Interfaces
hplayer.addInterface('http', 8080)
hplayer.addInterface('http2', 80, {'playlist': False, 'loop': False, 'mute': False})
hplayer.addInterface('serial', "^USB Single Serial")


# DEFAULT Loop
@hplayer.on('app-run')
@hplayer.on('playlist.end')
@hplayer.on('files.filelist-updated')
def play0(ev, *args):
    sampler.play("00_*.*", oneloop = True)

# LIST ON MEDIA
mediaON = []
onIndex = 0
@hplayer.on('files.filelist-updated')
def mediaON(ev, *args):
	global mediaON
	mediaON = hplayer.files.listFiles("ON_*.*")
	if not mediaON: mediaON = []
	print("[ON] MEDIA", mediaON)

# LIST OFF MEDIA
mediaOFF = []
offIndex = 0
@hplayer.on('files.filelist-updated')
def mediaOFF(ev, *args):
	global mediaOFF
	mediaOFF = hplayer.files.listFiles("OFF_*.*")
	if not mediaOFF: mediaOFF = []
	print("[OFF] MEDIA", mediaOFF)

# State: WAIT / START / ON / END // OFF 
state = "WAIT"

# prox
@hplayer.on('serial.prox')
def prox(ev, *args):

	global state, onIndex, mediaON, mediaOFF

	# ON detected
	if args[0] == 'ON':
		sampler.stop("OFF_*.*")

		# WAIT -> START
		if state == "WAIT":

			# play START
			state = "START"
			sampler.stop("ON_*.*")
			sampler.play("START_*.*", oneloop = False)
			
			# shuffle ON
			onIndex = 0
			mediaON = random.shuffle(mediaON)

		# OFF -> resume ON or START
		elif state == "OFF":
			sampler.stop("OFF_*.*")
			if sampler.isPlaying("ON_*.*"): 
				state = "ON"
				sampler.resume("ON_*.*")
			elif sampler.isPlaying("START_*.*"):
				state = "START"
				sampler.resume("START_*.*")
			else:
				state = "START"
				sampler.play("START_*.*", oneloop = False)

		# ALREADY ON or START: do Nothing..


		hplayer.interface('serial').send('/relay/1')

	elif args[0] == 'OFF':
		if sampler.isPlaying("ON_*.*"): 
			sampler.pause("ON_*.*")
		sampler.play("OFF_*.*")
		hplayer.interface('serial').send('/relay/0')


@hplayer.on('sampler.player0.media-end')
@hplayer.on('sampler.player1.media-end')
@hplayer.on('sampler.player2.media-end')
def player1(ev, *args):
	global state, onIndex, mediaON, mediaOFF

	if not args[0]: return
	media = args[0].split('/')[-1]

	# START END -> ON
	if media.startswith('START_'):
		state = "ON"
		sampler.stop("START_*.*")
		sampler.play(mediaON[onIndex], oneloop = True)
		onIndex = (onIndex + 1) % len(mediaON)
		print("ON END")


	if media.startswith('ON_'):
		print("ON END")
	elif media.startswith('OFF_'):
		print("OFF END")


# SERIAL events
@hplayer.on('serial.playsample')
def playsample(ev, *args):
    sampler.play( args[0]+"_*.*", oneloop = True )  # !!!! Nivard: False / Puzzle: True !!!!

@hplayer.on('serial.stopsample')
def playsample(ev, *args):
    sampler.stop( args[0]+"_*.*" )



# HTTP2 Logs
@hplayer.on('player.*')
@hplayer.on('sampler.*')
@hplayer.on('gpio.*')
@hplayer.on('serial.*')
def http2_logs(ev, *args):
	if ev.startswith('gpio') and ev.find('-') == -1: return 
	hplayer.interface('http2').send('logs', [ev]+list(args))

# RUN
hplayer.run()
