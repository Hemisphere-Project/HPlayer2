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
if hplayer.isRPi():
    player.addInterface('gpio', [21], 310)

# Remove default stop at "end-playlist" (or it prevent the next play !)
player.unbind('end-playlist', player.stop)

# HTTP + GPIO events
player.on(['push1', 'gpio21-on'], lambda: player.play("loop.*"))


# PATH
hplayer.setBasePath(["/data/media", "/mnt/usb"])
hplayer.persistentSettings("/data/hplayer2-flipper.cfg")

# DISABLE automations
def disableAuto(settings):
	player.loop(False)
	player.autoplay(False)
	player.clear()
player.on(['settings-applied'], disableAuto)

# SETTINGS (pre-start)
# player.audiomode('stereo')
# player.imagetime(15)

# RUN
hplayer.run()
