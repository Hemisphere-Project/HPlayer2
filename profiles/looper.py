from time import sleep
from core.engine.hplayer import HPlayer2


# INIT HPLAYER
hplayer = HPlayer2(mediaPath='/data/usb')

# PLAYERS
player 	= hplayer.addPlayer('mpv','looper')

# INTERFACES
#keypad 	= hplayer.addInterface('keypad')
#keypad.draw( [".:: HPlayer2 ::.", "   Starting "+keypad.CHAR_LOVE+"   "] )
sleep(2.0)  	# wait for USB to get ready

# LOOP usb
def playloop():
	sleep(1)
	hplayer.playlist.play('/data/usb')

# Ready -> player operational (no-op placeholder for clarity)
@player.on('ready')
def player_ready(ev, *args):
	pass

# Settings ready -> set loop and volume
@hplayer.on('app-run')
def init(ev, *args):
	hplayer.settings.set('volume', 100)
	hplayer.settings.set('loop', 2)
	playloop()

# Nomedia -> retry    
@hplayer.playlist.on('nomedia')
def retry(ev, *args):
		sleep(1)
		playloop()

# RUN
hplayer.run()
