from core.engine.hplayer import HPlayer2
from core.engine import network
import time

# EXTRA TMP UPLOAD
import tempfile
tempfile.tempdir = '/data/var/tmp'


# INIT HPLAYER
hplayer = HPlayer2('/data/media', '/data/hplayer2-gadagne21.cfg')



# PLAYER
player = hplayer.addPlayer('mpv', 'player')
player.imagetime(0)

player.doLog['events'] = False
# player.doLog['cmds'] = True


# Interfaces
hplayer.addInterface('http', 8080)
hplayer.addInterface('http2', 80, {'playlist': False, 'loop': False, 'mute': False})
if hplayer.isRPi():
    hplayer.addInterface('hcon', ['T1', 'T2'], 300)
    


# PLAY action with debouncer and click protection

debounceLastTime = 0
debounceLastMedia = ""

def doPlay(media, debounce=300):
    	
	# DEBOUNCE media
	global debounceLastTime, debounceLastMedia
	now = int(round(time.time() * 1000))
	if debounce > 0 and debounceLastMedia == media and (now - debounceLastTime) < debounce:
		return
	debounceLastTime = now
	debounceLastMedia = media

	hplayer.settings.set('mute', True)
	time.sleep(0.1)
	hplayer.playlist.play(media)
	time.sleep(0.05)
	hplayer.settings.set('mute', False)



# DEFAULT File
@hplayer.on('player.ready')
@hplayer.on('playlist.end')
def play0(ev, *args):
    doPlay("0_*.*")
    hplayer.interface('hcon').set('T5', True)

# TURN 1
@hplayer.on('http.turn1')
@hplayer.on('hcon.T1-on')
@hplayer.on('hcon.SW1-on')
def play1(ev, *args):
	doPlay("1_*.*", 1000)
	hplayer.interface('hcon').set('T5', False)
    
# TURN 2
@hplayer.on('http.turn2')
@hplayer.on('hcon.T2-on')
@hplayer.on('hcon.SW2-on')
def play1(ev, *args):
	doPlay("2_*.*", 1000)
	hplayer.interface('hcon').set('T5', False)

# TEST
@hplayer.on('hcon.SW3-on')
def play1(ev, *args):
	doPlay("3_*.*", 1000)
	hplayer.interface('hcon').set('T5', False)

# DISABLE some manual settings
@hplayer.on('settings.loading')
def disableAuto(ev, *args):
	hplayer.settings.set('loop', False)
	hplayer.settings.set('autoplay', False)
	hplayer.playlist.clear()


# HTTP2 Logs
@hplayer.on('player.*')
@hplayer.on('sampler.*')
@hplayer.on('gpio.*')
@hplayer.on('serial.*')
def http2_logs(ev, *args):
	if ev.startswith('gpio') and ev.find('-') == -1: return 
	hplayer.interface('http2').send('logs', [ev]+list(args))


# RUN
hplayer.run()
