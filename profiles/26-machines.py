from core.engine.hplayer import HPlayer2
import os
import tempfile

# 26-MACHINES — Machines expo trigger player (3x RPi, Arnaud's stock)
#
# Behavior:
#   0_* media          -> default loop (resumes whenever nothing else is asked)
#   /play/<N>          -> play N_* media, then back to the 0_* loop
#   /stop              -> back to the 0_* loop (or silence if no 0_* on card)
#
# Control surfaces:
#   HTTP  (port 80)    -> http://<ip>/play/1   http://<ip>/stop
#   OSC   (udp 4000)   -> /play/1  /stop                      (any player)
#                         /all/play/1  /all/stop              (broadcast, all players)
#                         /<hostname>/play/1  /<hostname>/stop (this player only)
#                         works unicast or broadcast; a scope naming another
#                         player is silently dropped. Args accepted as path
#                         segment (/play/1) or OSC argument (/play 1).
#   http2 (port 8080)  -> web UI, media management (upload to /data/media)

# On natural end of a triggered N_* piece: back to the 0_* loop.
# Set True to loop the triggered piece until an explicit /stop instead.
TRIG_LOOP = False

DEFAULT_PATTERN = '0_*.*'

# spool http2 uploads on the /data partition (not tmpfs /tmp: a media-sized
# upload would eat the RPi's RAM). The dir must exist or werkzeug's spooling crashes.
try:
	os.makedirs('/data/var/tmp', exist_ok=True)
except OSError:
	pass                                   # dev machine without /data: profile won't run anyway
tempfile.tempdir = '/data/var/tmp'

# INIT HPLAYER
hplayer = HPlayer2(['/data/media', '/data/usb'], '/data/hplayer2-26-machines.cfg')

# PLAYER
player = hplayer.addPlayer('mpv', 'player')

# INTERFACES
hplayer.addInterface('http', 80)            # trigger API: /play/<N> /stop
hplayer.addInterface('http2', 8080)         # web UI + media management
hplayer.addInterface('osc', 4000)           # trigger API, optionally scoped /all or /<hostname>

# Audio hub monitor: inert without the platform /etc/audiohub.conf contract
# (mpv picks the hub PCM by itself; this only feeds health chips to http2).
hplayer.addInterface('audiohub')

# /play and /stop carry profile semantics (N_* patterns, return-to-default):
# detach the stock autoBind handlers from both trigger surfaces so they don't
# race ours (http '/play/1' would otherwise playlist.play('1')).
for _iface in ('http', 'osc'):
	for _ev in ('play', 'stop'):
		for _func in hplayer.interface(_iface).listeners(_ev):
			hplayer.interface(_iface).off(_ev, _func)


# STATE
state = {'trig': None}      # pattern currently triggered, None = default loop


def playDefault():
	"""0_* loop if any 0_* media exists, silence otherwise"""
	state['trig'] = None
	hplayer.settings.set('loop', 2)
	if hplayer.files.listFiles(DEFAULT_PATTERN):
		hplayer.playlist.play(DEFAULT_PATTERN)
	else:
		hplayer.playlist.clear()           # emits 'stop' -> player stops


def playTrig(n):
	"""play N_* media; back to default on end (TRIG_LOOP: loop until /stop)"""
	if n is None or not str(n).isdigit():
		hplayer.log('play: invalid trigger', n)
		return
	pattern = str(n) + '_*.*'
	if not hplayer.files.listFiles(pattern):
		hplayer.log('play: no media matching', pattern)
		return
	state['trig'] = pattern
	hplayer.settings.set('loop', 2 if TRIG_LOOP else 0)
	hplayer.playlist.play(pattern)


# DEFAULT loop: at boot, when media appear/change, and when a triggered piece ends
@hplayer.on('app-run')
@hplayer.on('files.filelist-updated')
@hplayer.on('playlist.end')
def onDefault(ev, *args):
	# media changed while a triggered piece plays: don't interrupt it,
	# its end (or a /stop) lands on the fresh filelist anyway
	if ev.startswith('files.') and state['trig'] and player.isPlaying():
		return
	playDefault()


# HTTP trigger API
@hplayer.on('http.play')
def httpPlay(ev, *args):
	playTrig(args[0] if args else None)

@hplayer.on('http.stop')
def httpStop(ev, *args):
	playDefault()


# OSC trigger API
# addresses arrive as one event token: 'osc.' + path without leading slash,
# e.g. /all/play/1 -> 'osc.all/play/1'
OSC_COMMANDS = ('play', 'stop')

@hplayer.on('osc.*')
def oscRoute(ev, *args):
	parts = [p for p in ev.split('.', 1)[1].split('/') if p]
	if not parts:
		return

	# scope prefix: /all or /<my-hostname> stripped, another hostname = not for us
	if parts[0].lower() not in OSC_COMMANDS:
		if parts[0].lower() in ('all', hplayer.hostname().lower()):
			parts.pop(0)
		else:
			return
	if not parts:
		return

	cmd = parts.pop(0).lower()
	payload = parts if parts else [str(a) for a in args]

	if cmd == 'play':
		playTrig(payload[0] if payload else None)
	elif cmd == 'stop':
		playDefault()
	else:
		# scoped generic command (/all/volume/50, /<host>/pause, ...):
		# hand it back to the stock autoBind set
		hplayer.interface('osc').emit(cmd, *payload)


# http2 logs
@hplayer.on('player.*')
@hplayer.on('http.*')
@hplayer.on('osc.*')
@hplayer.on('audiohub.*')
def http2_logs(ev, *args):
	hplayer.interface('http2').send('logs', [ev]+list(args))


# RUN
hplayer.run()
