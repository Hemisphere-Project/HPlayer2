from core.engine import hplayer, network
import time

# EXTRA TMP UPLOAD
import tempfile
tempfile.tempdir = '/data/var/tmp'

# PLAYER
player = hplayer.addplayer('mpv', network.get_hostname())
player.doLog['events'] = True
player.doLog['cmds'] = True

# Interfaces
player.addInterface('http', 8080)
player.addInterface('http2', 80)
player.addInterface('gpio', [20,21,16,14,15,26], 310)
if "-sync" in network.get_hostname():
	player.addInterface('zyre', 'wlan0')

# Remove default stop at "end-playlist" (or it prevent the next play !)
player.unbind('end-playlist', player.stop)

# PLAY action
def doPlay(media):
	if "-sync" in network.get_hostname():
		if "-master" in network.get_hostname():
			player.getInterface('zyre').node.broadcast('/play', list(media), 200)
			print('doPLay: master.. broadcast')
		else:
			print('doPLay: slave.. do nothing')
	else:
		player.mute(True)
		time.sleep(0.1)
		player.play(media)
		time.sleep(0.05)
		player.mute(False)

# PLAY with super debounce  (ATTENTION: compatible avec 1 appel seulement)
superLastTime = 0
def superDebounce(media, timeout=1000):
	global superLastTime
	if (int(round(time.time() * 1000)) - superLastTime) > timeout:
		doPlay(media)
		superLastTime = int(round(time.time() * 1000))
		print("PLAU")


# DEFAULT File
player.on(['player-ready', 'end-playlist'], lambda: doPlay("0_*.*"))

# HTTP + GPIO events
player.on(['push1', 'gpio21-on'], lambda: doPlay("1_*.*"))
player.on(['push2', 'gpio20-on'], lambda: doPlay("2_*.*"))
player.on(['push3', 'gpio16-on'], lambda: doPlay("3_*.*"))

# GPIO on+off
player.on(['turn1', 'gpio26'], lambda state: superDebounce("1_*.*", 1000))

# GPIO RF Remote
def togglePlay(): 
	if player.isPlaying(): player.stop()
	else: doPlay("0_*.*")
player.on(['remote', 'gpio14-on', 'gpio15-on'], togglePlay)

# PATH
hplayer.setBasePath("/data/media")
hplayer.persistentSettings("/data/hplayer2-gadagne19.cfg")

# DISABLE automations
def disableAuto(settings):
	player.loop(False)
	player.autoplay(False)
	player.clear()
player.on(['settings-applied'], disableAuto)

# SETTINGS (pre-start)
player.imagetime(15)

# RUN
hplayer.run()
