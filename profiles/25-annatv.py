from core.engine.hplayer import HPlayer2
from core.engine import network
import os, types, time
from threading import Timer

# INIT HPLAYER
hplayer = HPlayer2(config=True, datadir='/data', mediaPath=['media'])

# PLAYER
player = hplayer.addPlayer('mpv', 'mpv')

# Interfaces
nowde = hplayer.addInterface('nowde', player)
keypad = hplayer.addInterface('keypad')

keypad.lcd.set_color( 100, 0, 100)
keypad.draw( [".:: HPlayer2 ::.", "   Starting "+keypad.CHAR_LOVE+"   "] )

# RSync USB (on start)
#
time.sleep(2.0)  	# wait for USB to get ready
usbCount = len([name for name in os.listdir('/data/usb') if os.path.isfile( os.path.join('/data/usb', name) )])
if usbCount > 0:
    
	keypad.draw( [".:: HPlayer2 ::.", "    USB sync    "] )
    
	class RepeatTimer(Timer):
		def run(self):
			while not self.finished.wait(self.interval):
				self.function(*self.args, **self.kwargs)
    
	blink = False
	def ledBLink():
		global blink
		blink = not blink
		if blink: keypad.lcd.set_color( 100, 100, 0)
		else: keypad.lcd.set_color( 100, 0, 0)
    
	timer = RepeatTimer(0.2, ledBLink)
	timer.start()
    
	ellapsed = time.time()
 
	hplayer.log("USB detected: syncing !")
	cmd = "rsync -rtv --exclude=\".*\" --delete /data/usb/ "+hplayer.mediaPath[0]
	hplayer.log(cmd)
	os.system(cmd)

	ellapsed = time.time()-ellapsed	
	if ellapsed < 2:
		print("WAIT", 2-ellapsed)
		time.sleep(2-ellapsed)
	timer.cancel()



holdCounter = 0
scrollSpeed = 3.08
introDuration = 1.5
blinkCounter = 0
blinkSpeed = 10


# PATCH Keypad LCD update
def lcd_update(self):
    
	global holdCounter, blinkCounter
	if holdCounter > 10:
		holdCounter = -1
		Timer(0.4, lambda: self.emit('hardreset')).start()
  
	if holdCounter < 0:
		self.lcd.set_color( 100, 0 , 0)
		return [".:: HPlayer2 ::.", "   restarting   "]
	
	lines = ["", ""]
 
	media = player.status()['media']
 
	# Line 0 : MEDIA
	playlistCount = str(hplayer.playlist.index()+1) + "/" + str(hplayer.playlist.size())	
	if media:
		lines[0] = keypad.CHAR_PLAY + playlistCount + " " 
		
		media = os.path.basename(media)[:-4]
		skroller3 = max(0, (player.position()*scrollSpeed) % len(media) - introDuration * scrollSpeed)
		offset = min( int(skroller3), len(media)-15 +len(lines[0]) )
		lines[0] += media[offset:]

	else:
		lines[0] = keypad.CHAR_STOP + playlistCount
	
	lines[0] = lines[0].ljust(16, ' ')[:16]
  

	# Line 1 : VOLUME
	lines[1] = keypad.CHAR_VOL +str(hplayer.settings.get('volume')).ljust(5, ' ')

	# Line 1 : WIFI
	lines[1] += keypad.CHAR_WIFI
	if network.get_essid('wlan0'): 
		lines[1] += (str( min(100, network.get_rssi('wlan0')) )+"%").ljust(6, ' ')
		blinkCounter = 1
	else: 
		lines[1] += "---% "
		blinkCounter = (blinkCounter+1) % blinkSpeed

	# COLORS
	if blinkCounter > 0: color = ( 100 if not media else 0 , 100, 100 if not media else 0)	# RED/GREEN: play state
	else: color = ( 0, 0 , 100)														# BLUE flash: no wifi
	
	self.lcd.set_color( *color )
  
	return lines

keypad.update = types.MethodType(lcd_update, keypad)


# RUN
hplayer.run()                               						# TODO: non blocking
