from time import sleep
from core.engine.hplayer import HPlayer2


# INIT HPLAYER
hplayer = HPlayer2('/data/usb')

# PLAYERS
player 	= hplayer.addPlayer('mpv','looper')

# INTERFACES
keypad 	= hplayer.addInterface('keypad')

keypad.draw( [".:: HPlayer2 ::.", "   Starting "+keypad.CHAR_LOVE+"   "] )
sleep(2.0)  	# wait for USB to get ready

# LOOP usb
def playloop():
	print("No Media... Retrying")
	sleep(1)
	hplayer.playlist.play('/data/usb')

# Ready -> set loop and volume
@player.on('ready')
def init(ev, *args):
    hplayer.settings.set('volume', 100)
    hplayer.settings.set('loop', 2)
    playloop()

# Nomedia -> retry    
@hplayer.playlist.on('nomedia')
def retry(ev, *args):
		playloop()

# RUN
hplayer.run()
