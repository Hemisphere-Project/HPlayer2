from core.engine.hplayer import HPlayer2
import os
import tempfile

# 26-MACHINES — Machines expo trigger player (3x RPi, Arnaud's stock)
#
# Behavior:
#   0_* media            -> default loop (resumes whenever nothing else plays)
#   /trig/<N>            -> play N_* media once, then back to the 0_* loop
#   /play/<media>        -> stock direct play, once, then back to the 0_* loop
#   /stop                -> back to the 0_* loop (silence if no 0_* on card)
#
# Control surfaces:
#   http2 (port 80)      -> web UI, media management (upload to /data/media)
#   HTTP  (port 8080)    -> http://<ip>:8080/trig/1   http://<ip>:8080/stop
#                           all stock commands available too (/play/<media>, /pause, ...)
#   OSC   (udp 4000)     -> /trig/1  /stop                       (any player)
#                           /all/trig/1  /all/stop               (broadcast, all players)
#                           /<hostname>/trig/1  /<hostname>/stop (this player only)
#                           the scoped form accepts any stock command (/all/volume/50);
#                           a scope naming another player is silently dropped. Args
#                           accepted as path segment (/trig/1) or OSC argument (/trig 1).

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
hplayer.addInterface('http2', 80)           # web UI + media management
hplayer.addInterface('http', 8080)          # trigger API: /trig/<N> /stop + stock commands
hplayer.addInterface('osc', 4000)           # trigger API, optionally scoped /all or /<hostname>

# Audio hub monitor: inert without the platform /etc/audiohub.conf contract
# (mpv picks the hub PCM by itself; this only feeds health chips to http2).
hplayer.addInterface('audiohub')


def playDefault():
	"""0_* loop if any 0_* media exists, silence otherwise"""
	hplayer.settings.set('loop', 2)
	if hplayer.files.listFiles(DEFAULT_PATTERN):
		hplayer.playlist.play(DEFAULT_PATTERN)
	else:
		hplayer.playlist.clear()           # emits 'stop' -> player stops


def playTrig(n):
	"""play N_* media once; playlist.end brings the 0_* loop back"""
	if n is None or not str(n).isdigit():
		hplayer.log('trig: invalid trigger', n)
		return
	pattern = str(n) + '_*.*'
	if not hplayer.files.listFiles(pattern):
		hplayer.log('trig: no media matching', pattern)
		return
	hplayer.settings.set('loop', 0)
	hplayer.playlist.play(pattern)


# DEFAULT loop: at boot, when media appear/change, and when a one-shot ends
@hplayer.on('app-run')
@hplayer.on('files.filelist-updated')
@hplayer.on('playlist.end')
def onDefault(ev, *args):
	# media changed while a one-shot (trig or direct play) is running:
	# don't interrupt it, its end lands on the fresh filelist anyway
	if ev.startswith('files.') and player.isPlaying() and hplayer.settings.get('loop') == 0:
		return
	playDefault()


# any direct play (stock handler did the playing) becomes a one-shot:
# force loop 0 so its natural end falls back to the 0_* loop above
@hplayer.on('http.play')
@hplayer.on('http2.play')
@hplayer.on('osc.play')
def oneShot(ev, *args):
	hplayer.settings.set('loop', 0)


# stop -> back to the default loop (the stock stop already halted the player
# by the time these bubble up; http2 stop stays a true stop for management)
@hplayer.on('http.stop')
@hplayer.on('osc.stop')
def onStop(ev, *args):
	playDefault()


# HTTP trigger
@hplayer.on('http.trig')
def httpTrig(ev, *args):
	playTrig(args[0] if args else None)


# OSC trigger + scope routing
# addresses arrive as one event token: 'osc.' + path without leading slash,
# e.g. /all/trig/1 -> 'osc.all/trig/1'
@hplayer.on('osc.*')
def oscRoute(ev, *args):
	parts = [p for p in ev.split('.', 1)[1].split('/') if p]
	if not parts:
		return

	head = parts.pop(0).lower()
	if head == 'trig':
		playTrig(parts[0] if parts else (str(args[0]) if args else None))
		return

	# not a scope for us: either a stock command (autoBind already handled it
	# on the interface) or another player's scope -> nothing to do
	if head not in ('all', hplayer.hostname().lower()) or not parts:
		return

	cmd = parts.pop(0).lower()
	if cmd == 'trig':
		playTrig(parts[0] if parts else (str(args[0]) if args else None))
	else:
		# scoped stock command (/all/stop, /all/volume/50, /<host>/pause, ...):
		# replay it unscoped on the interface for the stock autoBind set
		hplayer.interface('osc').emit(cmd, *(parts if parts else list(args)))


# http2 logs
@hplayer.on('player.*')
@hplayer.on('http.*')
@hplayer.on('osc.*')
@hplayer.on('audiohub.*')
def http2_logs(ev, *args):
	hplayer.interface('http2').send('logs', [ev]+list(args))


# RUN
hplayer.run()
