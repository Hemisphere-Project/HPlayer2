from core.engine.hplayer import HPlayer2
from core.engine import network
from datetime import datetime, timedelta
from threading import Timer
import subprocess
import time
import os

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
hplayer.addInterface('http2', 80, {'playlist': False, 'loop': False, 'mute': True})

# Zyre SYNC
SYNC = False
SYNC_MASTER = False
if os.path.isfile('/boot/wifi/eth0-sync-AP.nmconnection') or os.path.isfile('/boot/wifi/eth0-sync-STA.nmconnection'):
	SYNC = True
	SYNC_MASTER = os.path.isfile('/boot/wifi/eth0-sync-AP.nmconnection')
	hplayer.addInterface('zyre', 'eth0')

elif os.path.isfile('/boot/wifi/wlan0-sync-AP.nmconnection') or os.path.isfile('/boot/wifi/wlan0-sync-STA.nmconnection'):
	SYNC = True
	SYNC_MASTER = os.path.isfile('/boot/wifi/wlan0-sync-AP.nmconnection')
	if network.has_interface('wlan0'):
		hplayer.addInterface('zyre', 'wlan0')
	elif network.has_interface('wlan1'):
		hplayer.addInterface('zyre', 'wlan1')

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


currentDate = None
checkDayTimer = None

# RTC day changed
def checkDay(date=None):
	global checkDayTimer
	global currentDate

	if checkDayTimer:
			checkDayTimer.cancel()
	checkDayTimer = Timer(30, checkDay)
	checkDayTimer.start()

	try: 
		localDate = True

		if not date:
			date = subprocess.run(['hwclock', '--show'], stdout=subprocess.PIPE).stdout.decode('utf-8').strip().split('+')[0]
			date = datetime.strptime(date, '%Y-%m-%d %H:%M:%S.%f')
		else:
			localDate = False

		day_of_year = date.timetuple().tm_yday #tm_sec

		# send current date
		if SYNC and localDate:
			hplayer.interface('zyre').node.broadcast('date', (date+timedelta(days=0)).strftime("%Y-%m-%d"))	
			return False		

		# Check if day changed
		currentDay = currentDate.timetuple().tm_yday if currentDate else -1

		if currentDay == day_of_year: 
			print('Day not changed', currentDay)
			return False

		elif currentDate and date < currentDate:
			print('Old clock, ignoring.. ')
			return False
		
		currentDate = date
		currentDay = currentDate.timetuple().tm_yday if currentDate else -1
		print('Day changed to', currentDate.strftime("%Y-%m-%d"), currentDay)

		playDay()
		return True

	except Exception as e:
		print('RTC Error', e)
		return False

dayOffset = -7

# RTC Clock
def playDay():
	currentDay = currentDate.timetuple().tm_yday if currentDate else -1
	if currentDay >= 0:
		media = hplayer.files.currentList()
		doPlay(media[ (currentDay+dayOffset) % len(media) ])

# ON Date
@hplayer.on('zyre.date')
def extdate(ev, *args):
	global currentDate
	try:
		print("Ext date received")
		extdate = datetime.strptime(args[0], '%Y-%m-%d')
		if not currentDate or extdate > currentDate:
			checkDay(extdate)
	except Exception as e:
		print("Ext date error", e)

# DEFAULT File
@hplayer.on('app-run')
@hplayer.on('files.filelist-updated')
@hplayer.on('playlist.end')
def play0(ev, *args):
	hplayer.settings.set('loop', 2)
	# if not checkDay(): playDay()
	checkDay()

# HTTP2 Play -> disable loop && do propagate
@hplayer.on('http2.play')
def play2(ev, *args):
	global currentDate, checkDayTimer
	if checkDayTimer:
			checkDayTimer.cancel()
	doPlay(args[0])
	currentDate = None
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
