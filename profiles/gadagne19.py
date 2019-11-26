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
if hplayer.isRPi():
    player.addInterface('gpio', [20,21,16,14,15], 310)

# Remove default stop at "end-playlist" (or it prevent the next play !)
player.unbind('end-playlist', player.stop)

# PLAY action
def doPlay(media):
	player.mute(True)
	time.sleep(0.1)
	player.play(media)
	time.sleep(0.05)
	player.mute(False)


# DEFAULT File
player.on(['player-ready', 'end-playlist'], lambda: doPlay("0_*.*"))

# HTTP + GPIO events
player.on(['push1', 'gpio21-on'], lambda: doPlay("1_*.*"))
player.on(['push2', 'gpio20-on'], lambda: doPlay("2_*.*"))
player.on(['push3', 'gpio16-on'], lambda: doPlay("3_*.*"))

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
