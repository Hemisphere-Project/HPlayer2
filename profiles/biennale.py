from core.engine.hplayer import HPlayer2
from core.engine import network
import os
import time

# BIENNALE unified profile (merges biennale24.py + biennale26-wall.py)
#
# Per-device MODE, from /boot markers:
#   (no marker)                              -> SOLO : local play, loop
#   /boot/wifi/<iface>-sync-AP.nmconnection  -> SYNC master : zyre-synchronized start
#   /boot/wifi/<iface>-sync-STA.nmconnection -> SYNC slave
#
# WALL_SYNC below upgrades every SYNC device to continuous frame-lock
# (wallclock clock + chase servo, seamless mpv loop, slaves self-start
# if they boot after the master). Comment it out to fall back to the
# 2024 behavior: loop 0, the master re-broadcasts a synchronized play
# at every media end.
WALL_SYNC = True
# WALL_SYNC = False

# EXTRA TMP UPLOAD
# spool http2 uploads on the /data partition (not tmpfs /tmp: a media-sized upload
# would eat the RPi's RAM). The dir must exist or werkzeug's spooling crashes.
import tempfile
try:
	os.makedirs('/data/var/tmp', exist_ok=True)
except OSError:
	pass                                   # dev machine without /data: profile won't run anyway
tempfile.tempdir = '/data/var/tmp'

# MEDIA PATH
mediaPath = ['/data/media', '/data/usb']

# CHECK IF /etc/asound.conf contains "pcm.usb", otherwise copy from scripts/asound.conf-rpi3
if not os.path.isfile('/etc/asound.conf') or not open('/etc/asound.conf').read().find('pcm.usb') > -1:
	os.system('rw && cp /opt/HPlayer2/scripts/asound.conf-rpi3 /etc/asound.conf && sync && ro')

# INIT HPLAYER
hplayer = HPlayer2(mediaPath, '/data/hplayer2-biennale.cfg')


# PLAYER
player = hplayer.addPlayer('mpv', 'player')
player.imagetime(15)

player.doLog['events'] = True
player.doLog['cmds'] = False

PLAY_PATTERN = "[^1-9_]*.*"


# ROLE detection (same /boot/wifi marker convention as biennale24)
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

# (globals().get: commenting the WALL_SYNC line out entirely is safe)
WALL = bool(SYNC and SYNC_IFACE and globals().get('WALL_SYNC'))

if SYNC_MASTER: print("SYNC_MASTER!")
if WALL: print("WALL mode: continuous sync")


# Interfaces
hplayer.addInterface('http2', 80, {'playlist': False, 'loop': False, 'mute': True})

if SYNC and SYNC_IFACE:
	# Zyre: peer discovery, clockshift measurement, synchronized start
	hplayer.addInterface('zyre', SYNC_IFACE)

if WALL:
	# Wallclock: continuous position sync (master emits, slaves chase)
	hplayer.addInterface('wallclock', SYNC_IFACE, SYNC_MASTER)


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
			hplayer.interface('zyre').node.broadcast('stop')
			hplayer.interface('zyre').node.broadcast('play', media, SYNC_BUFFER)
			print('doPlay: sync master.. broadcast')
		else:
			print('doPlay: sync slave.. do nothing')

	# PLAY SOLO
	else:
		hplayer.playlist.play(media)

# SYNC_MASTER INIT: let slaves join zyre before the first broadcast
@hplayer.on('app-run')
def sync_init(ev, *args):
	if SYNC_MASTER:
		time.sleep(10)

# DEFAULT File
@hplayer.on('app-run')
@hplayer.on('files.filelist-updated')
@hplayer.on('playlist.end')
def play0(ev, *args):
	doPlay(PLAY_PATTERN)
	if WALL or not SYNC:
		hplayer.settings.set('loop', 2) # blackless loop (wall: mpv loop=inf below)
	else:
		hplayer.settings.set('loop', 0) # 2024 sync: re-broadcast a synced play each loop

# SYNC_MASTER INIT PART 2
@hplayer.on('app-run')
def sync_init2(ev, *args):
	if SYNC_MASTER:
		time.sleep(1)
		doPlay(PLAY_PATTERN)


# WALL: seamless loop + drifter arming + late-boot self-start
if WALL:
	@hplayer.on('player.playing')
	def wall_playing(ev, *args):
		# mpv loop=inf: blackless wrap, position wraps seamlessly on master
		# and slaves alike; the drifter only trims the residual drift.
		player._applyOneLoop(True)
		if not SYNC_MASTER:
			hplayer.interface('wallclock').drifter.arm()

	if not SYNC_MASTER:
		# Slave boots after the master: no play broadcast will ever come
		# (the master loops seamlessly, playlist.end never fires). The
		# drifter sees a playing master clock but a stopped player, and
		# calls this hook: self-start the pattern, then chase-lock.
		def wall_selfstart():
			print('wallclock: master is playing, self-starting', PLAY_PATTERN)
			hplayer.playlist.play(PLAY_PATTERN)
		hplayer.interface('wallclock').drifter.onStalled = wall_selfstart


if SYNC:
	# HTTP2 Ctrl unbind
	uev = ['play', 'pause', 'resume', 'stop'] + (['volume'] if WALL else [])
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
			hplayer.interface('zyre').node.broadcast('loop', [2 if WALL else 0], SYNC_BUFFER)

	if WALL:
		@hplayer.on('http2.volume')
		def vol2(ev, *args):
			hplayer.interface('zyre').node.broadcast('volume', args[0], 0)


# HTTP2 Logs
@hplayer.on('player.*')
@hplayer.on('sampler.*')
@hplayer.on('gpio.*')
@hplayer.on('serial.*')
@hplayer.on('wallclock.*')
def http2_logs(ev, *args):
	if ev.startswith('gpio') and ev.find('-') == -1: return
	if len(args) and args[0] == 'time': return
	if ev.endswith('.drift'): return
	hplayer.interface('http2').send('logs', [ev]+list(args))

# ─── RADAR proximity + SCHEDULE window (biennale-2026-module-radar) ──────────
# Both optional and self-activating:
#  - radar: the interface always listens on USB but only fires radar.enter once a
#    box (extra/arduino/radar_ld2450) actually streams targets. Outdoor players carry
#    only [1-9]_ pieces, so the default loop above matches nothing and they stay
#    silent until someone enters range; then the piece plays once (play-out).
#  - schedule: inert unless enabled from http2 AND an RTC is present (requireRtc).
RADAR_PATTERN = "[1-9]_*.*"

radar    = hplayer.addInterface('radar')
schedule = hplayer.addInterface('schedule', 30, True)   # requireRtc: gate only with a real clock

@hplayer.on('radar.enter')
def radar_trigger(ev, *args):
	if schedule.isOpen() and not player.isPlaying():
		hplayer.settings.set('loop', -1)     # play the proximity piece once
		doPlay(RADAR_PATTERN)

@hplayer.on('schedule.open')
def schedule_open(ev, *args):
	doPlay(PLAY_PATTERN)                      # resume default content when the window opens

@hplayer.on('schedule.close')
def schedule_close(ev, *args):
	if SYNC and SYNC_MASTER:
		hplayer.interface('zyre').node.broadcast('stop')
	elif not SYNC:
		player.stop()                        # go silent when the window closes

# persist radar + schedule tunables edited from the http2 web UI (interfaces read live)
for _k in ('radar-range', 'radar-width', 'radar-enter-ms', 'radar-leave-ms',
           'schedule-enable', 'schedule-open', 'schedule-close'):
	hplayer.on('http2.' + _k)(lambda ev, *a, k=_k: hplayer.settings.set(k, a[0]))

@hplayer.on('radar.*')
@hplayer.on('schedule.*')
def radar_schedule_logs(ev, *args):
	hplayer.interface('http2').send('logs', [ev] + list(args))

# ─── DMX conduite (biennale-2026-module-dmx) ─────────────────────────────────
# Self-activating like the radar: the interface always scans USB for a cheap
# FTDI->DMX adapter; with none plugged it just idles. When present it drives DMX
# from the sidecar conduite of the media currently playing (vague.mp4 -> vague.dmx),
# evaluated against the player's wall-synced clock, so DMX follows loops/seeks/sync.
dmx = hplayer.addInterface('dmx')

# persist dmx tunables edited from http2 (interface reads them live)
for _k in ('dmx-protocol', 'dmx-fps', 'dmx-filter'):
	hplayer.on('http2.' + _k)(lambda ev, *a, k=_k: hplayer.settings.set(k, a[0]))

@hplayer.on('dmx.*')
def dmx_logs(ev, *args):
	if ev.endswith('.status') or ev.endswith('.levels'): return   # high-rate: UI only
	hplayer.interface('http2').send('logs', [ev] + list(args))


# RUN
hplayer.run()
