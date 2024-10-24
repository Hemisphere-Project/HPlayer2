from core.engine.hplayer import HPlayer2
from core.engine import network
from datetime import datetime
from threading import Timer
import subprocess
import time

# EXTRA TMP UPLOAD
import tempfile
tempfile.tempdir = '/data/var/tmp'


# MEDIA PATH
mediaPath = ['/data/media', '/data/usb']

# INIT HPLAYER
hplayer = HPlayer2(mediaPath, '/data/hplayer2-biennale24.cfg')


# PLAYER
player = hplayer.addPlayer('mpv', 'player')
player.imagetime(86400) # 1 day

player.doLog['events'] = True
player.doLog['cmds'] = False


# Interfaces
hplayer.addInterface('http', 8080)
hplayer.addInterface('http2', 80, {'playlist': False, 'loop': False, 'mute': True})


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


currentDay = -1
checkDayTimer = None

# RTC day changed
def checkDay():
	global checkDayTimer
	global currentDay

	if checkDayTimer:
			checkDayTimer.cancel()
	checkDayTimer = Timer(30, checkDay)
	checkDayTimer.start()

	try:
		date = subprocess.run(['hwclock', '--show'], stdout=subprocess.PIPE).stdout.decode('utf-8').strip().split('+')[0]
		day_of_year = datetime.strptime(date, '%Y-%m-%d %H:%M:%S.%f').timetuple().tm_yday #tm_sec

		if currentDay == day_of_year: 
			# print('Day not changed', currentDay)
			return False

		currentDay = day_of_year
		print('Day changed to', currentDay)
		playDay()
		return True

	except Exception as e:
		print('RTC Error', e)
		return False

# RTC Clock
def playDay():
	media = hplayer.files.currentList()
	doPlay(media[currentDay%len(media)])


# DEFAULT File
@hplayer.on('app-run')
@hplayer.on('files.filelist-updated')
@hplayer.on('playlist.end')
def play0(ev, *args):
	hplayer.settings.set('loop', 2)
	if not checkDay(): playDay()

# HTTP2 Play -> disable loop && do propagate
@hplayer.on('http2.play')
def play2(ev, *args):
	global currentDay, checkDayTimer
	if checkDayTimer:
			checkDayTimer.cancel()
	doPlay(args[0])
	currentDay = -1
	checkDayTimer = Timer(5, checkDay)
	checkDayTimer.start()

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
