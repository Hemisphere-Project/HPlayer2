from core.engine.hplayer import HPlayer2
from core.engine import network
import os
import time

# EXTRA TMP UPLOAD
import tempfile
tempfile.tempdir = '/data/var/tmp'


# MEDIA PATH
mediaPath = ['/data/media', '/data/usb']

# INIT HPLAYER
hplayer = HPlayer2(mediaPath, '/data/hplayer2-biennale24.cfg')


# PLAYER
player = hplayer.addPlayer('mpv', 'player')
player.imagetime(15)

player.doLog['events'] = True
player.doLog['cmds'] = False


# Interfaces
hplayer.addInterface('http', 8080)
hplayer.addInterface('http2', 80, {'playlist': False, 'loop': False, 'mute': True})
hplayer.addInterface('serial', '^M5', 10)
#if hplayer.isRPi():
#    hplayer.addInterface('gpio', [21,20,16,26,14,15], 310)

# Zyre SYNC
SYNC = False
SYNC_MASTER = False
if os.path.isfile('/boot/wifi/eth0-sync-AP.nmconnection') or os.path.isfile('/boot/wifi/eth0-sync-STA.nmconnection'):
	SYNC = True
	SYNC_MASTER = os.path.isfile('/boot/wifi/eth0-sync-AP.nmconnection')
	hplayer.addInterface('zyre', 'eth0')

elif os.path.isfile('/boot/wifi/wlan0-sync-AP.nmconnection') or os.path.isfile('/boot/wifi/wlan0-sync-STA.nmconnection'):
	SYNC = True
	SYNC_MASTER = os.path.isfile('/boot/wifi/wlan0-sync-AP.nmconnection')
	hplayer.addInterface('zyre', 'wlan0')

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

	# PLAY SYNC -> forward to peers
	if SYNC:
		if SYNC_MASTER:
			hplayer.interface('zyre').node.broadcast('play', media, 200)
			print('doPLay: sync master.. broadcast')
		else:
			print('doPLay: sync slave.. do nothing')

	# PLAY SOLO
	else:
		hplayer.playlist.play(media)


# DEFAULT File
@hplayer.on('app-run')
@hplayer.on('files.filelist-updated')
@hplayer.on('playlist.end')
def play0(ev, *args):
	doPlay("[^1-9_]*.*")
	if not SYNC:
		hplayer.settings.set('loop', 2) # allow blackless loop on solo mode
	else:
		hplayer.settings.set('loop', 0)

# BTN 1
@hplayer.on('http.push1')
@hplayer.on('gpio.21-on')
def play1(ev, *args):
	hplayer.settings.set('loop', 0)
	doPlay("1_*.*")

# BTN 2
@hplayer.on('http.push2')
@hplayer.on('gpio.20-on')
def play1(ev, *args):
	hplayer.settings.set('loop', 0)
	doPlay("2_*.*")

# BTN 3
@hplayer.on('http.push3')
@hplayer.on('gpio.16-on')
def play1(ev, *args):
	hplayer.settings.set('loop', 0)
	doPlay("3_*.*")

# HTTP2 Play -> disable loop && do propagate
@hplayer.on('http2.play')
def play2(ev, *args):
	hplayer.settings.set('loop', 0)
	doPlay(args[0])

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
