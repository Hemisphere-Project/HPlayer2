from core.engine import hplayer, network

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
player.addInterface('serial', "^CP2102")

# SERIAL USB
player.on(['RELOOP'], lambda: player.play("loop*.*"))

# PATH
hplayer.setBasePath(["/mnt/usb"])
hplayer.persistentSettings("/data/hplayer2-flipper.cfg")

# DISABLE automations
def disableAuto(settings):
	player.loop(False)
	player.autoplay(False)
	player.clear()
player.on(['settings-applied'], disableAuto)


# RUN
hplayer.run()
