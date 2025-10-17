from core.engine.hplayer import HPlayer2
from core.engine import network
from platformdirs import user_data_dir
import os
import time

# Get platform-specific config directory
DATADIR = user_data_dir("HPlayer2", "Hemisphere")
os.makedirs(DATADIR, exist_ok=True)

# EXTRA TMP UPLOAD
import tempfile
tempfile.tempdir = DATADIR + '/tmp'
os.makedirs(tempfile.tempdir, exist_ok=True)

# MEDIA PATH
LOCALMEDIA = DATADIR + '/media'
os.makedirs(LOCALMEDIA, exist_ok=True)
mediaPath = [LOCALMEDIA]

# INIT HPLAYER
hplayer = HPlayer2(mediaPath, DATADIR+'/hplayer2.cfg')

# PLAYER
player = hplayer.addPlayer('mpv', 'player')
player.imagetime(15)

player.doLog['events'] = True
player.doLog['cmds'] = True


# Interfaces
# hplayer.addInterface('http', 8081)
hplayer.addInterface('http2', 8080, {'playlist': False, 'loop': False, 'mute': True})
# hplayer.addInterface('serial', '^M5', 10)


# PLAY action
debounceLastTime = 0
debounceLastMedia = ""

def doPlay(media, debounce=0):
    	
	# DEBOUNCE media
	global debounceLastTime, debounceLastMedia
	now = int(round(time.time() * 1000))
	if debounce > 0 and debounceLastMedia == media and (now - debounceLastTime) < debounce:
		return
	debounceLastTime = now
	debounceLastMedia = media

	hplayer.playlist.play(media)


# DEFAULT File
# @hplayer.on('app-run')
# @hplayer.on('files.filelist-updated')
# @hplayer.on('playlist.end')
# def play0(ev, *args):
# 	doPlay("[^1-9_]*.*")
# 	hplayer.settings.set('loop', 0)
		
  
# HTTP2 Logs
@hplayer.on('player.*')
@hplayer.on('sampler.*')
@hplayer.on('gpio.*')
@hplayer.on('serial.*')
def http2_logs(ev, *args):
	if ev.startswith('gpio') and ev.find('-') == -1: return 
	if len(args) and args[0] == 'time': return
	hplayer.interface('http2').send('logs', [ev]+list(args))

# RUN
hplayer.run()
