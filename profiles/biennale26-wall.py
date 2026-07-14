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
hplayer = HPlayer2(mediaPath, '/data/hplayer2-biennale26-wall.cfg')


# PLAYER
player = hplayer.addPlayer('mpv', 'player')
player.imagetime(15)

player.doLog['events'] = True
player.doLog['cmds'] = False


# ROLE detection (same /boot/wifi marker convention as the b24 wall):
# <iface>-sync-AP.nmconnection => master / <iface>-sync-STA.nmconnection => slave
SYNC_BUFFER = 200
SYNC = False
SYNC_MASTER = False
SYNC_IFACE = None
if os.path.isfile('/boot/wifi/eth0-sync-AP.nmconnection') or os.path.isfile('/boot/wifi/eth0-sync-STA.nmconnection'):
	SYNC = True
	SYNC_MASTER = os.path.isfile('/boot/wifi/eth0-sync-AP.nmconnection')
	SYNC_IFACE = 'eth0'

elif os.path.isfile('/boot/wifi/wlan0-sync-AP.nmconnection') or os.path.isfile('/boot/wifi/wlan0-sync-STA.nmconnection'):
	SYNC = True
	SYNC_MASTER = os.path.isfile('/boot/wifi/wlan0-sync-AP.nmconnection')
	if network.has_interface('wlan0'):
		SYNC_IFACE = 'wlan0'
	elif network.has_interface('wlan1'):
		SYNC_IFACE = 'wlan1'

if SYNC_MASTER: print("SYNC_MASTER!")


# Interfaces
hplayer.addInterface('http2', 80, {'playlist': False, 'loop': False, 'mute': True})

if SYNC and SYNC_IFACE:
	# Zyre: peer discovery, clockshift measurement, synchronized start
	hplayer.addInterface('zyre', SYNC_IFACE)
	# Wallclock: continuous position sync (master emits, slaves chase)
	hplayer.addInterface('wallclock', SYNC_IFACE, SYNC_MASTER)
else:
	print('WARNING: no /boot/wifi sync marker found -> solo mode (no wall sync)')


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

	# PLAY SYNC -> master broadcasts, slaves wait for the zyre order
	if SYNC:
		if SYNC_MASTER:
			hplayer.interface('zyre').node.broadcast('stop')
			hplayer.interface('zyre').node.broadcast('play', media, SYNC_BUFFER)
			print('doPlay: sync master.. broadcast')
		else:
			print('doPlay: sync slave.. do nothing')

	# PLAY SOLO
	else:
		hplayer.playlist.play(media)


# DEFAULT File
@hplayer.on('app-run')
@hplayer.on('playlist.end')
def play0(ev, *args):
	doPlay("[^1-9_]*.*")
	hplayer.settings.set('loop', 2)
	print('play0')


# SEAMLESS LOOP + CHASER ARMING
# mpv loop=inf: blackless wrap, the position wraps seamlessly on master and
# slaves alike; the wallclock chaser only trims the residual drift.
@hplayer.on('player.playing')
def playing(ev, *args):
	player._applyOneLoop(True)
	if SYNC and not SYNC_MASTER and hplayer.interface('wallclock'):
		hplayer.interface('wallclock').chaser.arm()


if SYNC:
	# HTTP2 Ctrl unbind
	uev = ['play', 'pause', 'resume', 'stop', 'volume']
	for ev in uev:
		for func in hplayer.interface('http2').listeners(ev):
			hplayer.interface('http2').off(ev, func)

	# HTTP2 Ctrl re-bind with Zyre broadcast
	@hplayer.on('http2.play')
	@hplayer.on('http2.pause')
	@hplayer.on('http2.resume')
	@hplayer.on('http2.stop')
	@hplayer.on('http2.volume')
	def ctrl2(ev, *args):
		ev = ev.replace('http2.', '')
		sync_b = SYNC_BUFFER
		if ev == 'volume': sync_b = 0
		if ev == 'play':
			hplayer.interface('zyre').node.broadcast('stop')
			args = [ a.split("_")[0]+'_*' if '_' in a else a for a in args ]  ### WARNING: missleading since it could trigger multiple files on self !
		if ev == 'volume':
			args = args[0]
		hplayer.interface('zyre').node.broadcast(ev, args, sync_b)
		if ev == 'play':
			hplayer.interface('zyre').node.broadcast('loop', [2], sync_b)


# HTTP2 Logs
@hplayer.on('player.*')
@hplayer.on('wallclock.*')
def http2_logs(ev, *args):
	if len(args) and args[0] == 'time': return
	if ev.endswith('.drift'): return
	hplayer.interface('http2').send('logs', [ev]+list(args))

# RUN
hplayer.run()
