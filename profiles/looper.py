from time import sleep
from core.engine import hplayer

# PLAYER
player = hplayer.addplayer('mpv', 'looper')

# INTERFACES
player.addInterface('keyboard').asIRremote()

def playloop():
	print("No Media... Retrying")
	sleep(1)
	player.play('*')

# INTERNAL events
player.on(['app-run', 'nomedia'], playloop)
player.loop(1)

# RUN
hplayer.setBasePath(["/mnt/usb"])
hplayer.run()
