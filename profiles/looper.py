from core.engine import hplayer

# PLAYER
player = hplayer.addplayer('mpv', 'looper')

def playloop():
	print("No Media... Retrying")
	sleep(1)
	player.play('*')

# INTERNAL events
player.on(['app-run', 'nomedia'], playloop)

# RUN
hplayer.setBasePath(["/media/usb", "/kxkm/media"])
hplayer.run()                               # TODO: non blocking
