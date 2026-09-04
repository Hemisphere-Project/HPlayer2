from core.engine.hplayer import HPlayer2
from core.engine import network
from core.interfaces.nowde import media_index_of
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

# AUDIO: the plumbing (ALSA hub graph, snd-aloop, forwarder units) belongs to
# the PLATFORM — Pi-tools audiohub module. HPlayer2 only detects the
# /etc/audiohub.conf contract (+/data override): present = play the hub + compensate its
# latency; absent = generic ALSA, audio config untouched (laptop/dev).

# INIT HPLAYER
hplayer = HPlayer2(mediaPath, '/data/hplayer2-biennale.cfg')


# PLAYER
player = hplayer.addPlayer('mpv', 'player')
player.imagetime(15)

player.doLog['events'] = True
player.doLog['cmds'] = False

PLAY_PATTERN = "[^1-9_]*.*"                  # the default loop: everything but the 1_..9_ one-shots

def default_pattern():
	# same content at boot, at schedule-open and on a Nowde master (Thomas 2026-09-04): the
	# whole non-1..9_ set, looping. Only the numeric prefix of the current file travels to the
	# Nowde slaves, so outdoor loop content is named 01_…, 02_… (zero-padded: index 1, 2, …).
	return PLAY_PATTERN

def nowde_slave():
	n = globals().get('nowde')
	return bool(n and n.role == 'slave')      # a Nowde master drives this player over CC#100/MTC

def schedule_open_now():
	s = globals().get('schedule')             # defined further down; disabled/no RTC = always open
	return (s is None) or s.isOpen()


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
	if nowde_slave():
		return                               # a Nowde master drives this player over CC#100
	if not schedule_open_now():
		return                               # booted (or restarted) outside the window: stay silent
	doPlay(default_pattern())
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
	if nowde_slave():
		return
	if schedule.isOpen() and not player.isPlaying():
		hplayer.settings.set('loop', -1)     # play the proximity piece once
		doPlay(RADAR_PATTERN)

# Nowde topology: only the MASTER's clock counts. Its stop/play reaches the slaves as
# MEDIA_SYNC state 0/1 -> CC#100 0/N, so a slave ignores its own schedule (RTC or not).
@hplayer.on('schedule.open')
def schedule_open(ev, *args):
	if nowde_slave():
		return
	doPlay(default_pattern())                 # resume default content when the window opens

@hplayer.on('schedule.close')
def schedule_close(ev, *args):
	if nowde_slave():
		return
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

# ─── NOWDE ESP-NOW sync (biennale-2026-module-radar, lot 2: the 6 outdoor players) ──
# Self-activating like the radar: the interface idles until a "Nowde - XXXXXX" USB-MIDI
# node shows up, then the NODE's role picks the leg (its HELLO says master or slave):
#  - master node (AtomS3, LCD): this player loops its default content as usual (PLAY_PATTERN,
#    same as boot / schedule-open) and the interface streams {index, position, state} to the
#    node, which relays it over ESP-NOW. The index is the numeric prefix of the current file.
#  - slave node (AtomS3 Lite): CC#100 picks the clip by numeric prefix, MTC drives the
#    Drifter chase-lock. play0 above is skipped on a slave; the master's CC#100 drives it.
# Content contract: zero-padded numeric prefixes on every unit (01_xxx.mp4 on the master and
# the slaves; 1_ alone is the one-shot set), same index = same cue, same duration if the
# master loops a single file seamlessly. Distinct from the wifi wall (wallclock).
nowde = hplayer.addInterface('nowde', player)

if nowde:
	@hplayer.on('nowde.role')
	def nowde_role(ev, *args):
		if args[0] == 'master':
			hplayer.settings.set('loop', 2)  # blackless loop of the whole default set
			if not schedule_open_now():
				return                       # outside the window: schedule.open will start it
			if not player.isPlaying():
				doPlay(default_pattern())    # the role arrived after app-run: same start as boot

	@hplayer.on('player.playing')
	def nowde_playing(ev, *args):
		# A single-file loop wraps seamlessly in mpv (loop=inf): the master's position wraps
		# without a black and the slave's Drifter rides the wrap. Several files: let the
		# playlist advance (loop 2) so the index changes and the slaves switch with it.
		if nowde.role:
			player._applyOneLoop(hplayer.playlist.size() <= 1)

	# persist nowde tunables edited from the http2 web UI (interface reads them live)
	for _k in ('nowde-layer', 'nowde-index-default', 'nowde-jumpfix', 'nowde-dance', 'nowde-nodelog'):
		hplayer.on('http2.' + _k)(lambda ev, *a, k=_k: hplayer.settings.set(k, a[0]))

	@hplayer.on('nowde.*')
	def nowde_logs(ev, *args):
		if ev.endswith('.qf') or ev.endswith('.ff') or ev.endswith('.receivers'): return   # high-rate
		if ev.endswith('.nodelog'): return                                                # journal only
		if ev.endswith('.status'):
			hplayer.interface('http2').send('nowde-status', args[0])
			return
		hplayer.interface('http2').send('logs', [ev] + list(args))

# CoreS3 USB remote (teleco2): intentionally NOT loaded on biennale players
# (Thomas 2026-07-21). The radar box (extra/arduino/radar_ld2450) shares the
# generic Espressif 303a:1001 ROM-CDC id with the CoreS3 remote, and teleco2's
# hardcoded "HPlayer2|303a:1001" filter would grab the radar box and starve the
# radar interface. Biennale uses no remote; teleco2 still lives in profiles/anna.py.

# Audio hub monitor: watches the platform forwarder units + USB card, pushes
# per-output health to the http2 chips, and applies the latency compensation.
# Mode policy: WALL leads the drifter chase by the pipeline latency while mpv
# delays video by the same amount -> frames AND speakers land on the wallclock
# (mixed hub/non-hub fleets stay aligned). Start-sync (2024 mode) has no
# drifter to lead, so it keeps VISUAL priority: no compensation, audio runs
# the pipeline latency late (under the perception edge). Solo compensates.
audiohub = hplayer.addInterface('audiohub')

if audiohub:
	if SYNC and not WALL:
		audiohub.compensate = False
	if WALL and hplayer.interface('wallclock'):
		# Only slaves carry a drifter (the master emits the clock and has
		# none by design) — first WALL-master + audiohub boot crashed here
		# (mixed bench test, 2026-07-22).
		_drifter = hplayer.interface('wallclock').drifter
		if _drifter:
			_drifter.offset = audiohub.latency()

# persist dmx tunables edited from http2 (interface reads them live)
for _k in ('dmx-protocol', 'dmx-fps', 'dmx-filter'):
	hplayer.on('http2.' + _k)(lambda ev, *a, k=_k: hplayer.settings.set(k, a[0]))

@hplayer.on('dmx.*')
def dmx_logs(ev, *args):
	if ev.endswith('.status') or ev.endswith('.levels'): return   # high-rate: UI only
	hplayer.interface('http2').send('logs', [ev] + list(args))

@hplayer.on('audiohub.*')
def audiohub_logs(ev, *args):
	hplayer.interface('http2').send('logs', [ev] + list(args))


# RUN
hplayer.run()
