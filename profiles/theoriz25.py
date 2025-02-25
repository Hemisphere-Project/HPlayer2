from core.engine.hplayer import HPlayer2
from core.engine import network
import os
import time

# EXTRA TMP UPLOAD
import tempfile
tempfile.tempdir = '/data/var/tmp'

# MEDIA PATH
mediaPath = ['/data/media', '/data/usb']

# CHECK IF /etc/asound.conf contains "pcm.usb", otherwise copy from scripts/asound.conf-rpi3
if not os.path.isfile('/etc/asound.conf') or not open('/etc/asound.conf').read().find('pcm.usb') > -1:
	os.system('rw && cp /opt/HPlayer2/scripts/asound.conf-rpi3 /etc/asound.conf && sync && ro')

# INIT HPLAYER
hplayer = HPlayer2(mediaPath, '/data/hplayer2-biennale24.cfg')


# PLAYER
player = hplayer.addPlayer('mpv', 'player')
player.imagetime(36000)

player.doLog['events'] = True
player.doLog['cmds'] = False


# Interfaces
hplayer.addInterface('keyboard')
hplayer.addInterface('http2', 80, {'playlist': False, 'loop': False, 'mute': True})

# Zyre SYNC
SYNC_BUFFER = 100
SYNC = False
SYNC_MASTER = False
if os.path.isfile('/boot/wifi/eth0-sync-AP.nmconnection') or os.path.isfile('/boot/wifi/eth0-sync-STA.nmconnection'):
	SYNC = True
	SYNC_MASTER = os.path.isfile('/boot/wifi/eth0-sync-AP.nmconnection')
	hplayer.addInterface('zyre', 'eth0')

elif os.path.isfile('/boot/wifi/wlan0-sync-AP.nmconnection') or os.path.isfile('/boot/wifi/wlan0-sync-STA.nmconnection'):
	SYNC = True
	SYNC_MASTER = os.path.isfile('/boot/wifi/wlan0-sync-AP.nmconnection')
	if network.has_interface('wlan0'):
		hplayer.addInterface('zyre', 'wlan0')
	elif network.has_interface('wlan1'):
		hplayer.addInterface('zyre', 'wlan1')

# PLAY action
debounceLastTime = 0
debounceLastMedia = ""

def doPlay():

	global keyMode

	if keyMode == -1:
		media = "[^0-9_]*.*"
		loop = 0
	else:
		media = str(keyMode)+"_*.*"
		loop = 2
    	
	# PLAY SYNC -> forward to peers
	if SYNC:
		if SYNC_MASTER:
			hplayer.interface('zyre').node.broadcast('stop')
			hplayer.interface('zyre').node.broadcast('play', media, SYNC_BUFFER)
			hplayer.interface('zyre').node.broadcast('loop', str(loop), SYNC_BUFFER)
			print('doPLay: sync master.. broadcast')
		else:
			print('doPLay: sync slave.. do nothing')

	# PLAY SOLO
	else:
		hplayer.playlist.play(media)
  
    

# SYNC_MASTER INIT
@hplayer.on('app-run')
def sync_init(ev, *args):
	if SYNC_MASTER:
		time.sleep(10)

# keyMode: -1 -> SYNC Master loop everyones on !0-9_ media
# keyMode: 0-9 -> Everyones plays in local loop his 0-9_ media  
keyMode = -1

# DEFAULT File
@hplayer.on('app-run')
@hplayer.on('files.filelist-updated')
@hplayer.on('playlist.end')
def play0(ev, *args):
	doPlay()
 

@hplayer.on('zyre.keyb')
def keybremote(ev, *args):
	global keyMode
	if SYNC_MASTER:
		keyMode = args[0]
		doPlay()

@hplayer.on('keyboard.*')
def keyb(ev, *args):
	global keyMode

	# process keyboard
	base, key = ev.split("keyboard.KEY_")
	if not key: return
	key, mode = key.split("-")
	if key.startswith('KP'): 
		key = key[2:]
	
	# 0 -> 9
	if key.isdigit() and mode == 'down':
		numk = int(key)
		keyMode = numk
	# ENTER    
	elif key == 'ENTER' and mode == 'down':
		keyMode = -1
	# NOT INTERESTED
	else:
		return

	# send via zyre
	if SYNC:
		hplayer.interface('zyre').node.broadcast('keyb', [keyMode])
	else:
		doPlay()
    
		
# SYNC_MASTER INIT PART 2
@hplayer.on('app-run')
def sync_init2(ev, *args):
	if SYNC_MASTER:
		time.sleep(1)
		doPlay()



if SYNC:
	# HTTP2 Ctrl unbind
	uev = ['play', 'pause', 'resume', 'stop']
	for ev in uev:
		for func in hplayer.interface('http2').listeners(ev):
			hplayer.interface('http2').off(ev, func)

	# HTTP2 Ctrl re-bind with Zyre
	@hplayer.on('http2.play')
	@hplayer.on('http2.pause')
	@hplayer.on('http2.resume')
	@hplayer.on('http2.stop')
	def ctrl2(ev, *args):
		ev = ev.replace('http2.', '')
		if ev == 'play':
			hplayer.interface('zyre').node.broadcast('stop')
		hplayer.interface('zyre').node.broadcast(ev, args, SYNC_BUFFER)
		if ev == 'play':
			hplayer.interface('zyre').node.broadcast('loop', [0], SYNC_BUFFER)
		


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
