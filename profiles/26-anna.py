from core.engine.hplayer import HPlayer2
from core.engine import network
from core.interfaces.wallclock import end_action

import os, sys, types, platform, time
from threading import Timer

# ─────────────────────────────────────────────────────────────────────────────────────────
#  26-anna — the Anna players, 2026 (anna-players#t-017).            starter: hplayer2@26-anna
#
#  Outdoor audio, ~15 players that move, NO fixed master: any keypad, the numpad or the
#  CoreS3 remote orders the whole parc over zyre, and every player executes every order.
#  The player that gave the LAST transport order emits the position clock and the others
#  chase it (wallclock role='elected', hplayer2#t-086); a player that missed an order
#  catches up from that clock (media, stop, pause). A silent leader is replaced after 8 s.
#
#  What changed from profiles/anna.py (kept as it was for the 6.8.1 fleet):
#   - sync on `wint` (the 7.3 image's internal WiFi; `wlan0` on older images)
#   - wallclock role='elected' + health(restart=False): repairs only, never a black-out
#   - orders through wallclock.order(): play/stop/pause/resume carry the sender's rank and
#     the 300 ms zyre buffer, so every player changes state at the same instant
#   - track end: ONE advance, by the clock leader, decided by the track's NAME on every node
#     (`_loop` replays, `_stop` stops) — replaces masterLoopIndex and its `_loop` race
#   - keypad LCD: the short-name scroll clamp (hplayer2#t-083), a `*` on the leader
# ─────────────────────────────────────────────────────────────────────────────────────────

# DIRECTORY / FILE
profilename = os.path.basename(__file__).split('.')[0]
base_path = ['/data/media', '/data/usb']
cfg_path = "/data/hplayer2-" + profilename + ".cfg"
FRESH_CFG = not os.path.isfile(cfg_path)

# INIT HPLAYER
hplayer = HPlayer2(base_path, cfg_path)

# PLAYERS
player 	= hplayer.addPlayer('mpv', 'mpv')

# SYNC INTERFACE: the 7.3 image renames the internal WiFi `wint` (udev, brcmfmac); Anna has no dongle
SYNC_IFACE = 'wint' if network.has_interface('wint') else 'wlan0'
hplayer.log("sync interface:", SYNC_IFACE)

# Interfaces
# health first: its thread-starvation guard must be in place before the others start threads.
# restart=False: a player is never restarted mid-show — a follower with no matching media, or any
# follower of a paused fleet, reads "not locked" for as long as that lasts, and that is fine.
health		= hplayer.addInterface('health', restart=False)
zyre		= hplayer.addInterface('zyre', SYNC_IFACE)
wallclock	= hplayer.addInterface('wallclock', SYNC_IFACE, role='elected')
# Audio is heard: the Drifter's default dead zone (enter 25 ms, exit 80 ms) lets a follower park up
# to 80 ms off its leader, audible on co-located speakers (Anna bench, 2026-11-06). 10/30 holds
# without hunting now that the elected follower compares like with like (Drifter.posAge); desk:
# t_tight_deadzone_join. Joins still JUMP first (seekThreshold 2 s): the dead zone only sets the end.
if getattr(wallclock, 'drifter', None):
	wallclock.drifter.deadZoneEnter = 0.010
	wallclock.drifter.deadZoneExit = 0.030
keypad 		= hplayer.addInterface('keypad')
http		= hplayer.addInterface('http', 8037)
keyboard 	= hplayer.addInterface('keyboard')
teleco2		= hplayer.addInterface('teleco2', False, SYNC_IFACE)	# USB remote (M5Stack CoreS3): parc orders, our WiFi

if keypad.lcd: keypad.lcd.set_color( 100, 0, 100)
keypad.draw( [".:: HPlayer2 ::.", "   Starting "+keypad.CHAR_LOVE+"   "] )
time.sleep(2.0)  	# wait for USB to get ready


# RSync USB (on start)
#
usbSync = os.path.exists('/data/usb/sync') and os.path.isdir('/data/usb/sync')

if usbSync:
	keypad.draw( [".:: HPlayer2 ::.", "    USB sync    "] )

	class RepeatTimer(Timer):
		def run(self):
			while not self.finished.wait(self.interval):
				self.function(*self.args, **self.kwargs)

	blink = False
	def ledBLink():
		global blink
		blink = not blink
		if not keypad.lcd: return
		if blink: keypad.lcd.set_color( 100, 100, 0)
		else: keypad.lcd.set_color( 100, 0, 0)

	timer = RepeatTimer(0.2, ledBLink)
	timer.start()

	ellapsed = time.time()

	hplayer.log("USB sync folder detected: syncing !")
	cmd = "rsync -tdv --delete --exclude='.*' --exclude='*/' --exclude='Thumbs.db' /data/usb/sync/ "+base_path[0]
	hplayer.log(cmd)
	os.system(cmd)

	ellapsed = time.time()-ellapsed
	if ellapsed < 2:
		time.sleep(2-ellapsed)
	timer.cancel()
else:
	hplayer.log("No USB sync folder detected, skipping sync !")


# Settings: no loop, no playlist advance — the profile owns the track end (below).
# Settings load inside run(): re-assert there, and seed a fresh card at the 6.8.1 fleet's level.
hplayer.settings.set('loop', -1)

@hplayer.on('app-run')
def seed_settings(ev, *args):
	hplayer.settings.set('loop', -1)
	if FRESH_CFG:
		hplayer.settings.set('volume', 95)
		hplayer.log("fresh settings file: volume 95 (the 6.8.1 fleet's level)")
	# The media folder IS the playlist, at every boot. settings.load() (in run(), just before app-run)
	# replays the stored 'playlist' key as do-playlist, and hplayer's own binding runs playlist.load()
	# on it: None (a fresh card) empties the list built at import (LCD 0/0, next/play dead), and a
	# stored list is stale once the USB sync's rsync --delete changed /data/media (index sync breaks).
	# Rebuild from the folder now that settings are ready: this also stores the folder's list.
	build_list()


# Orders to the whole parc, over zyre
#
# play / stop / pause / resume: buffered 300 ms (every player changes state at the same instant)
# and, through wallclock.order(), stamped with this player's rank: it becomes the clock leader.
# volume: immediate and unranked (it never moves the clock).
# auto=True (track end only): ranked as an advance, never as an order, tagged with the track it ends.
def broadcast(path, *args, auto=False, source=None):
	if path.startswith('play'):
		event, delay = 'unbuf_' + path, 300		# 'unbuf_': handled below, never by hplayer's own play*
	elif path in ('stop', 'pause', 'resume'):
		event, delay = path, 300
	else:
		event, delay = path, 0
	node = getattr(zyre, 'node', None) if zyre else None
	if node and wallclock:
		wallclock.order(event, list(args), delay, auto=auto, source=source)
	elif node:
		node.broadcast(event, list(args), delay)
	elif zyre:
		# zyre not up yet (no address at boot, up to 90 s): this player alone, like biennale's
		# zbroadcast — the elected clock realigns it once the node is up
		hplayer.log('[zyre] node not up yet:', event, 'handled locally')
		zyre.emit(event, *args)


# Build playlist: the whole media folder, navigated by index
#
@hplayer.files.on('file-changed')
@hplayer.files.on('filelist-updated')
def build_list(ev=None, *args):
	hplayer.playlist.load( hplayer.files.currentList() )
build_list()


# Zyre orders -> this player
#
@hplayer.on('zyre.unbuf_playindex')
def unbuf_playindex(ev, *args):
	hplayer.playlist.emit('playindex', args[0])

@hplayer.on('zyre.unbuf_playz')
def unbuf_playz(ev, *args):
	hplayer.playlist.emit('playindex', hplayer.playlist.findIndex(str(args[0])+"_*") )


# Track end: ONE advance for the parc — the clock leader's (or a follower's whose leader has been
# silent 2 s: a dead leader never ends the show). Decided by the track's name, the same on every
# node: `_loop` replays it, `_stop` stops, anything else moves on, nothing after the last track.
#
@hplayer.on('playlist.end')
def track_end(ev, *args):
	if wallclock and not wallclock.mayAdvance():
		return
	idx = hplayer.playlist.index()
	track = hplayer.playlist.trackAtIndex(idx)
	act = end_action(track)
	if act == 'loop':
		broadcast('playindex', idx, auto=True, source=track)
	elif act == 'next' and idx < hplayer.playlist.size() - 1:
		broadcast('playindex', idx + 1, auto=True, source=track)


# Transport actions, parc-wide (shared by keypad / http / numpad / teleco2 remote)
#
introDuration = 1.5

def go_prev():
	if player.isPlaying() and player.position() > introDuration:
		broadcast('playindex', hplayer.playlist.index())		# rewind the current track
	else:
		broadcast('playindex', hplayer.playlist.prevIndex())

def go_next():
	broadcast('playindex', hplayer.playlist.nextIndex())

def go_stop():
	broadcast('stop')

def go_playindex(index):
	broadcast('playindex', index)

def go_playpause():
	if player.isPlaying():
		broadcast('resume' if player.isPaused() else 'pause')
	else:
		go_playindex(max(0, hplayer.playlist.index()))


# HTTP play
@hplayer.on('http.playh')
def http_playh(ev, *args):
	if len(args) > 0:
		go_playindex(int(args[0]))


# Keyboard (numpad)
#
for _n in range(10):
	hplayer.on('keyboard.KEY_KP%d-down' % _n, lambda ev, n=_n: broadcast('playz', n))
hplayer.on('keyboard.KEY_KPENTER-down',     lambda ev: go_stop())

hplayer.on('keyboard.KEY_KPPLUS-down', 		lambda ev: broadcast('volume', hplayer.settings.get('volume')+1))
hplayer.on('keyboard.KEY_KPPLUS-hold', 		lambda ev: broadcast('volume', hplayer.settings.get('volume')+1))
hplayer.on('keyboard.KEY_KPMINUS-down', 	lambda ev: broadcast('volume', hplayer.settings.get('volume')-1))
hplayer.on('keyboard.KEY_KPMINUS-hold', 	lambda ev: broadcast('volume', hplayer.settings.get('volume')-1))


# Keylock
#
keylock = True
canToggle = True
lockAlertCounter = 0

def lockAlert():
  global lockAlertCounter
  if (keylock): lockAlertCounter = 10
  else: lockAlertCounter = -10
  return

def toggleLock():
	global keylock, canToggle
	keylock = not keylock
	canToggle = False
	lockAlert()

def checkHoldLock():
  if canToggle and upHold and downHold: toggleLock()

upHold = False
downHold = False

# Bind Keypad / GPIO events
#
@hplayer.on('keypad.left')
@hplayer.on('keypad.left-hold')
def prev(ev, *args):
	if keylock:
		return lockAlert()
	go_prev()

@hplayer.on('keypad.right')
@hplayer.on('keypad.right-hold')
def next(ev, *args):
	if keylock:
		return lockAlert()
	go_next()

@hplayer.on('keypad.up')
@hplayer.on('keypad.up-hold')
def up(ev, *args):
	if ev == 'keypad.up-hold':
		global upHold
		upHold = True
		checkHoldLock()
	if lockAlertCounter < 0:
		return
	if keylock:
		return lockAlert()
	broadcast('volume', hplayer.settings.get('volume')+1)

@hplayer.on('keypad.up-release')
def releaseup(ev, *args):
	global upHold
	upHold = False

@hplayer.on('keypad.down')
@hplayer.on('keypad.down-hold')
def down(ev, *args):
	if ev == 'keypad.down-hold':
		global downHold
		downHold = True
		checkHoldLock()
	if lockAlertCounter < 0:
		return
	if keylock:
		return lockAlert()
	broadcast('volume', hplayer.settings.get('volume')-1)

@hplayer.on('keypad.down-release')
def releasedown(ev, *args):
	global downHold
	downHold = False

@hplayer.on('keypad.select')
def select(ev, *args):
	if keylock:
		return lockAlert()
	go_stop()

@hplayer.on('keypad.select-hold')
def select_hold(ev, *args):
	if keylock:
		return lockAlert()
	global holdCounter
	if holdCounter >= 0:
			holdCounter+=1

holdCounter = 0
scrollSpeed = 3.08
blinkCounter = 0
blinkSpeed = 10


# USB remote (teleco2 / M5Stack CoreS3) — has its own screen lock, not gated by keylock
#
hplayer.on('teleco2.remote-prev', 		lambda ev, *a: go_prev())
hplayer.on('teleco2.remote-next', 		lambda ev, *a: go_next())
hplayer.on('teleco2.remote-stop', 		lambda ev, *a: go_stop())
hplayer.on('teleco2.remote-playindex', 	lambda ev, *a: go_playindex(int(a[0])))
hplayer.on('teleco2.remote-playpause', 	lambda ev, *a: go_playpause())
hplayer.on('teleco2.remote-volup', 		lambda ev, *a: broadcast('volume', hplayer.settings.get('volume')+1))
hplayer.on('teleco2.remote-voldown', 	lambda ev, *a: broadcast('volume', hplayer.settings.get('volume')-1))


# PATCH Keypad LCD update
def lcd_update(self):

	global holdCounter, blinkCounter
	if holdCounter > 10:
		holdCounter = -1
		Timer(0.4, lambda: self.emit('hardreset')).start()

	if holdCounter < 0:
		self.lcd.set_color( 100, 0 , 0)
		return [".:: HPlayer2 ::.", "   restarting   "]

	global lockAlertCounter, canToggle
	if lockAlertCounter > 0:
		lockAlertCounter -= 1
		return ["... Locked ! ...", "                "]
	elif lockAlertCounter < 0:
		lockAlertCounter += 1
		return [".. Unlocked ! ..", "                "]
	else:
		canToggle = True

	lines = ["", ""]

	media = player.status()['media']

	# Line 0 : MEDIA
	playlistCount = str(hplayer.playlist.index()+1) + "/" + str(hplayer.playlist.size())
	if media:
		lines[0] = keypad.CHAR_PLAY + playlistCount + " "

		media = os.path.basename(media)[:-4]
		skroller3 = max(0, (player.position()*scrollSpeed) % len(media) - introDuration * scrollSpeed)
		# clamp at 0 (hplayer2#t-083): a name shorter than the window made the offset negative,
		# and media[negative:] showed only its tail — `01_intro` read `ro`
		offset = max(0, min( int(skroller3), len(media)-15 +len(lines[0]) ))
		lines[0] += media[offset:]

	else:
		lines[0] = keypad.CHAR_STOP + playlistCount

	lines[0] = lines[0].ljust(16, ' ')[:16]


	# Line 1 : VOLUME
	lines[1] = keypad.CHAR_VOL +str(hplayer.settings.get('volume')).ljust(5, ' ')

	# Line 1 : WIFI
	lines[1] += keypad.CHAR_WIFI
	if network.get_essid(SYNC_IFACE):
		lines[1] += (str( min(100, network.get_rssi(SYNC_IFACE)) )+"%").ljust(5, ' ')
		blinkCounter = 1
	else:
		lines[1] += "---% "
		blinkCounter = (blinkCounter+1) % blinkSpeed

	# Line 1 : ZYRE peers (0 until the node is built: no address yet at boot), `*` while this player emits the clock
	_zn = getattr(zyre, 'node', None) if zyre else None
	lines[1] += keypad.CHAR_PEERS +str(len(_zn.book) if _zn else 0).ljust(2, ' ')[:2]
	lines[1] += '*' if (wallclock and wallclock.isLeader()) else ' '

	# Another card carries our name: say it, in red, with the full name, until one is renamed
	if wallclock and getattr(wallclock, 'dupName', False):
		self.lcd.set_color( 100, 0, 0)
		return ["!! NAME TAKEN !!", network.get_hostname()[:16].ljust(16)]

	# COLORS
	if blinkCounter > 0: color = ( 100 if not media else 0 , 100, 100 if not media else 0)	# RED/GREEN: play state
	else: color = ( 0, 0 , 100)														# BLUE flash: no wifi

	self.lcd.set_color( *color )

	return lines

# Never let a display error kill the keypad thread (its loop has no guard: the LCD and every key
# would be dead until a restart) — keep the last good screen and say it once a minute
_lcdLast = [[".:: HPlayer2 ::.", "                "]]
_lcdErrAt = [0.0]
def lcd_update_safe(self):
	try:
		_lcdLast[0] = lcd_update(self)
	except Exception as e:
		if time.time() - _lcdErrAt[0] > 60:
			_lcdErrAt[0] = time.time()
			hplayer.log('keypad LCD update failed:', repr(e))
	return _lcdLast[0]

keypad.update = types.MethodType(lcd_update_safe, keypad)


# RUN
hplayer.run()                               						# TODO: non blocking
