from core.engine.hplayer import HPlayer2
from core.engine import network
import time

# EXTRA TMP UPLOAD
import tempfile
tempfile.tempdir = '/data/var/tmp'


# MEDIA PATH
mediaPath = '/data/media'
# if SYNC:
#     mediaPath = '/data/sync'

# INIT HPLAYER
hplayer = HPlayer2(mediaPath, '/data/hplayer2-biennale24.cfg')


# PLAYER
player = hplayer.addPlayer('mpv', 'player')
player.imagetime(15)

player.doLog['events'] = True
player.doLog['cmds'] = True


# Interfaces
hplayer.addInterface('http', 8080)
hplayer.addInterface('http2', 80, {'playlist': True, 'loop': True, 'mute': True})
# hplayer.addInterface('serial', "^CP2102", 20)
if hplayer.isRPi():
    hplayer.addInterface('gpio', [21,20,16,26,14,15], 310)
if "-sync" in network.get_hostname():
    	hplayer.addInterface('zyre')



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

	# PLAY SYNC -> forward to peers
	if "-sync" in network.get_hostname():
		if "-master" in network.get_hostname():
			hplayer.interface('zyre').node.broadcast('playzinc', media, 200)
			print('doPLay: master.. broadcast')
		else:
			print('doPLay: slave.. do nothing')

	# PLAY SOLO
	else:
		# hplayer.settings.set('mute', True)
		# time.sleep(0.1)
		hplayer.playlist.play(media)
		# time.sleep(0.05)
		# hplayer.settings.set('mute', False)


# PLAY sync on peer 
@hplayer.on('zyre.playzinc')
def playZ(ev, *args):
	media = args[0]
	# media = args[0].replace('*.*', network.get_hostname().split('-sync')[0]+'*.*')
	# hplayer.settings.set('mute', True)
	# time.sleep(0.1)
	hplayer.playlist.play(media)
	# time.sleep(0.05)
	# hplayer.settings.set('mute', False)


# # DEFAULT File
# @hplayer.on('player.ready')
# @hplayer.on('playlist.end')
# def play0(ev, *args):
#     doPlay("0_*.*")

# # BTN 1
# @hplayer.on('http.push1')
# @hplayer.on('gpio.21-on')
# def play1(ev, *args):
#     doPlay("1_*.*")

# # BTN 2
# @hplayer.on('http.push2')
# @hplayer.on('gpio.20-on')
# def play1(ev, *args):
#     doPlay("2_*.*")

# # BTN 3
# @hplayer.on('http.push3')
# @hplayer.on('gpio.16-on')
# def play1(ev, *args):
#     doPlay("3_*.*")

# HTTP2 Logs
@hplayer.on('player.*')
@hplayer.on('sampler.*')
@hplayer.on('gpio.*')
@hplayer.on('serial.*')
def http2_logs(ev, *args):
	if ev.startswith('gpio') and ev.find('-') == -1: return 
	if args[0] == 'time': return
	hplayer.interface('http2').send('logs', [ev]+list(args))

# RUN
hplayer.run()