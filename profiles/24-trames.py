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
sampler = hplayer.addSampler('mpv', 'sampler', 4)

# Interfaces
hplayer.addInterface('http', 8080)
hplayer.addInterface('http2', 80, {'playlist': False, 'loop': False, 'mute': False})
hplayer.addInterface('serial', "^USB Single Serial")


# LIST OFF MEDIA
offIndex = 0
mediaOFF = []
def makePlaylistOFF():
	global mediaOFF, offIndex
	offIndex = 0
	mediaOFF = hplayer.files.listFiles("OFF_*.*")
	if not mediaOFF: mediaOFF = []
	print("[OFF] MEDIA", mediaOFF)

# MAKE PLAYLIST
mediaIndex = 0
mediaList = []
def makePlaylist():
	global mediaList, mediaIndex
	mediaIndex = 0

	# ON media
	mediaList = hplayer.files.listFiles("ON_*.*")
	random.shuffle( mediaList )

	# prepend one START_ media
	startMedia = hplayer.files.listFiles("START_*.*")
	random.shuffle( startMedia )
	if startMedia and len(startMedia) > 0:
		mediaList.insert(0, startMedia[0])

	# append one END_ media
	endMedia = hplayer.files.listFiles("END_*.*")
	random.shuffle( endMedia )
	if endMedia and len(endMedia) > 0:
		mediaList.append(endMedia[0])

	print("[Playlist]", mediaList)


# Reset on files change
ready = False
@hplayer.on('files.filelist-updated')
@hplayer.on('app-run')
def resetState(ev=None, *args):
	global state, ready
	if ev == 'app-run': ready = True
	if not ready: return

	state = "WAIT"
	sampler.stop()
	hplayer.interface('serial').send('/relay/1')
	makePlaylist()
	makePlaylistOFF()

	# Wait loop
	sampler.play("00_*.*", oneloop = True, index = 0)
	sampler.play("WAIT_*.*", oneloop = True, index = 1)

# State: WAIT / ON // OFF 

# prox
@hplayer.on('serial.prox')
def prox(ev, *args):

	global state, mediaIndex, mediaList, mediaOFF, offIndex

	# ON detected
	if args[0] == 'ON':
		sampler.play("00_*.*", oneloop = True, index = 0)
		
		# PLAY or RESUME
		if state == "WAIT" or not sampler.isPlaying(index = 1): 
			mediaIndex = 0
			sampler.play(mediaList[mediaIndex], oneloop = False, index = 1)
		else:
			sampler.resume(index = 1)

		state = "ON"
		hplayer.interface('serial').send('/relay/1')

	# OFF detected
	elif args[0] == 'OFF' and state == "ON":
		if sampler.isPlaying(index = 1): 
			sampler.pause(index = 1)

		print("OFF", offIndex, mediaOFF[offIndex])
		sampler.play(mediaOFF[offIndex], oneloop = False, index = 0)
		offIndex = (offIndex + 1) % len(mediaOFF)
		
		state = "OFF"
		hplayer.interface('serial').send('/relay/0')


@hplayer.on('sampler.player0.media-end')
def loop0(ev, *args):
	print("END0", ev, args)
	if len(args) > 0 and args[0].split('/')[-1].startswith("OFF_"):
		print("END0: reset")
		resetState()
	else:	
		sampler.play("00_*.*", oneloop = True, index = 0)

@hplayer.on('sampler.player1.media-end')
def nextMedia(ev, *args):
	global state, mediaIndex, mediaList

	if state == "ON":
		mediaIndex += 1
		if mediaIndex < len(mediaList):
			sampler.play(mediaList[mediaIndex], index = 1)
		else:
			resetState()



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
