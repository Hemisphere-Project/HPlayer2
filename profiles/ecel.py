from core.engine.hplayer import HPlayer2
from core.engine import network

import os, sys, types, platform, time, math
from threading import Timer

# DIRECTORY / FILE
profilename = os.path.basename(__file__).split('.')[0]
base_path = ['/data/media']

# INIT HPLAYER
hplayer = HPlayer2(base_path, "/data/hplayer2-"+profilename+".cfg")

# PLAYERS
player 	= hplayer.addPlayer('mpv','mpv')

# Interfaces
keypad 		= hplayer.addInterface('keypad')
gpio			= hplayer.addInterface('gpio', [21], 310, 100, 'PDOWN')
# zyre		= hplayer.addInterface('zyre', 'wlan0')
# osc		= hplayer.addInterface('osc', 4000).hostOut = '10.0.0.255'
# http		= hplayer.addInterface('http', 8037)
# http2		= hplayer.addInterface('http2', 8080)
# keyboard 	= hplayer.addInterface('keyboard')

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
		if blink: keypad.lcd.set_color( 1, 0, 1)
		else: keypad.lcd.set_color( 0, 0, 0)
    
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
@hplayer.on('*.playz')
def play_indexed(ev, *args):
    hplayer.playlist.emit('playindex', hplayer.playlist.findIndex(str(args[0])+"_*") )


# Bind Keypad / GPIO events
#
@hplayer.on('keypad.left')
@hplayer.on('keypad.left-hold')
def prev(ev, *args):
    if player.isPlaying() and player.position() > introDuration:
        hplayer.playlist.emit('playindex', hplayer.playlist.index())
    else:
        hplayer.playlist.emit('playindex', hplayer.playlist.prevIndex())

@hplayer.on('gpio.21-off')        
@hplayer.on('keypad.right')
@hplayer.on('keypad.right-hold')
def next(ev, *args):
    print(ev)
    hplayer.playlist.emit('playindex', hplayer.playlist.nextIndex())

@hplayer.on('keypad.up')
@hplayer.on('keypad.up-hold')
def up(ev, *args):
    hplayer.playlist.emit('volume', hplayer.settings.get('volume')+1)

@hplayer.on('keypad.down')
@hplayer.on('keypad.down-hold')
def down(ev, *args):
    hplayer.playlist.emit('volume', hplayer.settings.get('volume')-1)
    
@hplayer.on('keypad.select')
def down(ev, *args):
    hplayer.playlist.emit('stop')
    global holdCounter
    holdCounter = 0

    
@hplayer.on('keypad.select-hold')
def down(ev, *args):
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
		self.lcd.set_color( 0, 0 , 0)
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
	lines[1] = keypad.CHAR_VOL +str(hplayer.settings.get('volume')).ljust(4, ' ')
 
	# Line 1: PROGRESS
	ctime = math.floor(player.status('time'))
	ctime = str(math.floor(ctime/60)).rjust(2, '0')+':'+str(math.floor(ctime%60)).rjust(2, '0')              
 
	lines[1] += ctime.rjust(11, ' ') 


	# COLORS
	color = ( 1 if not media else 0 , 0 , 1 if media else 0)	# RED/GREEN: play state	
	self.lcd.set_color( *color )
  
	return lines

keypad.update = types.MethodType(lcd_update, keypad)


# RUN
hplayer.run()                               						# TODO: non blocking
