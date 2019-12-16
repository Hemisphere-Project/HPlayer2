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
player.addInterface('zyre', 'eth0')
player.addInterface('http', 8080)
player.addInterface('http2', 80)

# Remove default stop at "end-playlist" (or it prevent the next play !)
player.unbind('end-playlist', player.stop)

# PLAY action
def doPlay(media):
	player.getInterface('zyre').node.broadcast('/play', list(media), 434)


# DEFAULT File
player.on(['player-ready', 'end-playlist'], lambda: doPlay("0_*.*"))

# PATH
hplayer.setBasePath("/data/media")
hplayer.persistentSettings("/data/hplayer2-gadagne19-sync.cfg")

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
