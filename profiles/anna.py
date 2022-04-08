from core.engine.hplayer import HPlayer2
from core.engine import network

import os, sys, types, platform, time
from threading import Timer

# DIRECTORY / FILE
profilename = os.path.basename(__file__).split('.')[0]
base_path = ['/data/media']

# INIT HPLAYER
hplayer = HPlayer2(base_path, "/data/hplayer2-"+profilename+".cfg")

# PLAYERS
player 	= hplayer.addPlayer('mpv','mpv')

# Interfaces
zyre		= hplayer.addInterface('zyre', 'wlan0')
keypad 		= hplayer.addInterface('keypad')
# osc		= hplayer.addInterface('osc', 4000).hostOut = '10.0.0.255'
# http		= hplayer.addInterface('http', 8037)
# http2		= hplayer.addInterface('http2', 8080)
# keyboard 	= hplayer.addInterface('keyboard')

keypad.lcd.set_color( 100, 0, 100)
keypad.draw( [".:: HPlayer2 ::.", "   Starting "+keypad.CHAR_LOVE+"   "] )
time.sleep(2.0)  	# wait for USB to get ready

# RSync USB (on start)
#
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
	cmd = "rsync -rtv --delete /data/usb/ "+base_path[0]
	hplayer.log(cmd)
	os.system(cmd)

	ellapsed = time.time()-ellapsed	
	if ellapsed < 2:
		print("WAIT", 2-ellapsed)
		time.sleep(2-ellapsed)
	timer.cancel()


# No Loop, neither playlist
hplayer.settings.set('loop', -1)


# Build playlist
#
@hplayer.files.on('file-changed')
def bulid_list(ev=None, *args):
    hplayer.playlist.load(base_path[0])
bulid_list()


# Zyre play index
@hplayer.on('zyre.playz')
def play_indexed(ev, *args):
    hplayer.playlist.emit('playindex', hplayer.playlist.findIndex(str(args[0])+"_*") )


# Broadcast Order on OSC/Zyre to other Pi's
#
def broadcast(path, *args):
	# print(path, list(args))
	if path.startswith('play'):
		zyre.node.broadcast(path, list(args), 300)   ## WARNING LATENCY !!
	else:
		zyre.node.broadcast(path, list(args))


# Keyboard
#
hplayer.on('keyboard.KEY_KP0-down', 		lambda ev: broadcast('playz', 0))
hplayer.on('keyboard.KEY_KP1-down', 		lambda ev: broadcast('playz', 1))
hplayer.on('keyboard.KEY_KP2-down', 		lambda ev: broadcast('playz', 2))
hplayer.on('keyboard.KEY_KP3-down', 		lambda ev: broadcast('playz', 3))
hplayer.on('keyboard.KEY_KP4-down', 		lambda ev: broadcast('playz', 4))
hplayer.on('keyboard.KEY_KP5-down', 		lambda ev: broadcast('playz', 5))
hplayer.on('keyboard.KEY_KP6-down', 		lambda ev: broadcast('playz', 6))
hplayer.on('keyboard.KEY_KP7-down', 		lambda ev: broadcast('playz', 7))
hplayer.on('keyboard.KEY_KP8-down', 		lambda ev: broadcast('playz', 8))
hplayer.on('keyboard.KEY_KP9-down', 		lambda ev: broadcast('playz', 9))
hplayer.on('keyboard.KEY_KPENTER-down',     lambda ev: broadcast('stop'))

hplayer.on('keyboard.KEY_KPPLUS-down', 		lambda ev: broadcast('volume', hplayer.settings.get('volume')+1))
hplayer.on('keyboard.KEY_KPPLUS-hold', 		lambda ev: broadcast('volume', hplayer.settings.get('volume')+1))
hplayer.on('keyboard.KEY_KPMINUS-down', 	lambda ev: broadcast('volume', hplayer.settings.get('volume')-1))	
hplayer.on('keyboard.KEY_KPMINUS-hold', 	lambda ev: broadcast('volume', hplayer.settings.get('volume')-1))	


# Keylock
#
keylock = True
canToggle = True
lockAlertCounter = 0

def lockAlert():
  global lockAlertCounter
  if (keylock): lockAlertCounter = 10
  else: lockAlertCounter = -10
  return

def toggleLock():
	global keylock, canToggle
	keylock = not keylock
	canToggle = False
	lockAlert()
 
def checkHoldLock():
  if canToggle and upHold and downHold: toggleLock()
  
upHold = False
downHold = False

# Bind Keypad / GPIO events
#
@hplayer.on('keypad.left')
@hplayer.on('keypad.left-hold')
def prev(ev, *args):
	if keylock: 
		return lockAlert()
	if player.isPlaying() and player.position() > introDuration:
			broadcast('playindex', hplayer.playlist.index())
	else:
			broadcast('playindex', hplayer.playlist.prevIndex())
        
@hplayer.on('keypad.right')
@hplayer.on('keypad.right-hold')
def next(ev, *args):
	if keylock: 
		return lockAlert()
	broadcast('playindex', hplayer.playlist.nextIndex())

@hplayer.on('keypad.up')
@hplayer.on('keypad.up-hold')
def up(ev, *args):
	if ev == 'keypad.up-hold':
		global upHold
		upHold = True
		checkHoldLock()
	if lockAlertCounter < 0:
		return
	if keylock: 
		return lockAlert()
	broadcast('volume', hplayer.settings.get('volume')+1)
 
@hplayer.on('keypad.up-release')
def releaseup(ev, *args):
	global upHold
	upHold = False

@hplayer.on('keypad.down')
@hplayer.on('keypad.down-hold')
def down(ev, *args):
	if ev == 'keypad.down-hold':
		global downHold
		downHold = True
		checkHoldLock()
	if lockAlertCounter < 0:
		return
	if keylock: 
		return lockAlert()
	broadcast('volume', hplayer.settings.get('volume')-1)
 
@hplayer.on('keypad.down-release')
def releasedown(ev, *args):
	global downHold
	downHold = False
    
@hplayer.on('keypad.select')
def down(ev, *args):
	if keylock: 
		return lockAlert()
	broadcast('stop')
    
@hplayer.on('keypad.select-hold')
def select(ev, *args):
	if keylock: 
		return lockAlert()
	global holdCounter 
	if holdCounter >= 0: 
			holdCounter+=1
    
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

	global lockAlertCounter, canToggle
	if lockAlertCounter > 0:
		lockAlertCounter -= 1
		return ["... Locked ! ...", "                "]
	elif lockAlertCounter < 0:
		lockAlertCounter += 1
		return [".. Unlocked ! ..", "                "]
	else: 
		canToggle = True
	
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
	
	# Line 1 : ZYRE
	lines[1] += keypad.CHAR_PEERS +str(zyre.activeCount()).ljust(2, ' ')[:2]+" "

	# COLORS
	if blinkCounter > 0: color = ( 100 if not media else 0 , 100, 100 if not media else 0)	# RED/GREEN: play state
	else: color = ( 0, 0 , 100)														# BLUE flash: no wifi
	
	self.lcd.set_color( *color )
  
	return lines

keypad.update = types.MethodType(lcd_update, keypad)


# RUN
hplayer.run()                               						# TODO: non blocking
