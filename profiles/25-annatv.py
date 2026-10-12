from core.engine.hplayer import HPlayer2
from profiles._common_anna import StatusLCD
import os, time
from threading import Timer

# INIT HPLAYER
hplayer = HPlayer2(config=True, datadir='/data', mediaPath=['media', 'usb'])

# PLAYER
player = hplayer.addPlayer('mpv', 'mpv')

# Interfaces
nowde = hplayer.addInterface('nowde', player)
keypad = hplayer.addInterface('keypad')

keypad.lcd.set_color( 100, 0, 100)
keypad.draw( [".:: HPlayer2 ::.", "   Starting "+keypad.CHAR_LOVE+"   "] )

# RSync USB (on start)
#
# time.sleep(2.0)  	# wait for USB to get ready
# usbCount = len([name for name in os.listdir('/data/usb') if os.path.isfile( os.path.join('/data/usb', name) )])
# if usbCount > 0:
    
# 	keypad.draw( [".:: HPlayer2 ::.", "    USB sync    "] )
    
# 	class RepeatTimer(Timer):
# 		def run(self):
# 			while not self.finished.wait(self.interval):
# 				self.function(*self.args, **self.kwargs)
    
# 	blink = False
# 	def ledBLink():
# 		global blink
# 		blink = not blink
# 		if blink: keypad.lcd.set_color( 100, 100, 0)
# 		else: keypad.lcd.set_color( 100, 0, 0)
    
# 	timer = RepeatTimer(0.2, ledBLink)
# 	timer.start()
    
# 	ellapsed = time.time()
 
# 	hplayer.log("USB detected: syncing !")
# 	cmd = "rsync -rtv --exclude=\".*\" --delete /data/usb/ "+hplayer.mediaPath[0]
# 	hplayer.log(cmd)
# 	os.system(cmd)

# 	ellapsed = time.time()-ellapsed	
# 	if ellapsed < 2:
# 		print("WAIT", 2-ellapsed)
# 		time.sleep(2-ellapsed)
# 	timer.cancel()



# PATCH Keypad LCD update (shared with anna, see profiles/_common_anna.py)
lcd = StatusLCD(hplayer, player, keypad)
keypad.update = lcd.update


# RUN
hplayer.run()                               						# TODO: non blocking
