from core.engine.hplayer import HPlayer2
from core.engine import network
import os
import time
from termcolor import colored

# EXTRA TMP UPLOAD
import tempfile
tempfile.tempdir = '/data/var/tmp'

# MEDIA PATH
mediaPath = ['/data/media', '/data/usb']

# INIT HPLAYER
hplayer = HPlayer2(mediaPath, '/data/hplayer2-biennale24.cfg')


# PLAYER
player = hplayer.addPlayer('mpv', 'player')
player.imagetime(15)

player.doLog['events'] = True
player.doLog['cmds'] = False


# Interfaces
# hplayer.addInterface('http', 8080)
hplayer.addInterface('http2', 80, {'playlist': False, 'loop': False, 'mute': True})
hplayer.addInterface('mtc', "rtpmidid")

# hplayer.addInterface('serial', '^M5', 10)
#if hplayer.isRPi():
#    hplayer.addInterface('gpio', [21,20,16,26,14,15], 310)

# Zyre SYNC
SYNC_OFFSET = 0
SYNC_BUFFER = 200
SYNC = False
SYNC_MASTER = False
if os.path.isfile('/boot/wifi/eth0-sync-AP.nmconnection') or os.path.isfile('/boot/wifi/eth0-sync-STA.nmconnection'):
	SYNC = True
	SYNC_MASTER = os.path.isfile('/boot/wifi/eth0-sync-AP.nmconnection')
	hplayer.addInterface('zyre', 'eth0', SYNC_OFFSET)

elif os.path.isfile('/boot/wifi/wlan0-sync-AP.nmconnection') or os.path.isfile('/boot/wifi/wlan0-sync-STA.nmconnection'):
	SYNC = True
	SYNC_MASTER = os.path.isfile('/boot/wifi/wlan0-sync-AP.nmconnection')
	if network.has_interface('wlan0'):
		hplayer.addInterface('zyre', 'wlan0', SYNC_OFFSET)
	elif network.has_interface('wlan1'):
		hplayer.addInterface('zyre', 'wlan1', SYNC_OFFSET)

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
	if SYNC:
		if SYNC_MASTER:
			hplayer.interface('zyre').node.broadcast('stop')
			hplayer.interface('zyre').node.broadcast('play', media, SYNC_BUFFER)
			print('doPLay: sync master.. broadcast')
		else:
			print('doPLay: sync slave.. do nothing')

	# PLAY SOLO
	else:
		hplayer.playlist.play(media)

# SYNC_MASTER INIT
@hplayer.on('app-run')
def sync_init(ev, *args):
	if SYNC_MASTER:
		time.sleep(10)

# DEFAULT File
@hplayer.on('app-run')
# @hplayer.on('files.filelist-updated')
@hplayer.on('playlist.end')
def play0(ev, *args):
	doPlay("[^1-9_]*.*")
	if not SYNC:
		hplayer.settings.set('loop', 2) # allow blackless loop on solo mode
	else:
		hplayer.settings.set('loop', 0)
	print('play0')

# SYNC_MASTER INIT PART 2
@hplayer.on('app-run')
def sync_init2(ev, *args):
	if SYNC_MASTER:
		time.sleep(1)
		# hplayer.interface('zyre').node.broadcast('stop', None, SYNC_BUFFER)
		# time.sleep(3)
		#doPlay('/data/media/test_pattern_1080x30-CBD.mp4')
		doPlay("[^1-9_]*.*")
		#hplayer.interface('zyre').node.broadcast('play',  '/data/media/test_pattern_1080x30-CBD.mp4', SYNC_BUFFER)
		

if SYNC:
	# HTTP2 Ctrl unbind
	uev = ['play', 'pause', 'resume', 'stop']
	for ev in uev:
		for func in hplayer.interface('http2').listeners(ev):
			hplayer.interface('http2').off(ev, func)

	# HTTP2 Ctrl re-bind with Zyre
	@hplayer.on('http2.play')
	@hplayer.on('http2.pause')
	@hplayer.on('http2.resume')
	@hplayer.on('http2.stop')
	def ctrl2(ev, *args):
		ev = ev.replace('http2.', '')
		if ev == 'play':
			hplayer.interface('zyre').node.broadcast('stop')
		hplayer.interface('zyre').node.broadcast(ev, args, SYNC_BUFFER)
		if ev == 'play':
			hplayer.interface('zyre').node.broadcast('loop', [0], SYNC_BUFFER)
		

#
# MTC
#

lastSpeed = 1.0
lastPos = -1
didJump = False
jumpFix = 300       # compensate the latency of jump (300ms for RockPro64 on timecode jump I.E. looping)

@hplayer.on('mtc.qf')
def f(ev, *args):
    global lastSpeed, lastPos, didJump, jumpFix

    doLog = True

    pos = player.position()

    # Check if player time is actually ellapsing
    if pos == lastPos or not player.isPlaying():
        # if doLog:
        #     print(str(args[0]), end="\t")
        #     print("no news from player.. dropping timecode tracking on this frame")
        return
    lastPos = pos

    clock = round(args[0].float, 2)
    diff = clock-pos

    speed = 1.0

    # framebuffer corrector
    #fix = 0.04    # compensate mtc latency from clock to tc tracker (typically 1 frame on Ubuntu x64 using Alsa Midi:Thru)
    fix = 0

    #jump
    if diff > 10 or diff < -2:
        player.seekTo(clock*1000+jumpFix)
        didJump = True
        print(str(args[0]), end="\t")
        print("timedelay=" + colored(round(diff,2),"red"), end="\t")
        print("JumpFix", jumpFix)

    else:   

        # Jump correction
        if didJump:
            didJump = False
            # Correcting JumpFix is dangerous: might diverge on different jump position / media quality / ...
            # if abs(diff+fix) > 0.01:
            #     jumpFix += min( max(-300, (diff+fix)*1000), 300)
            #     print("corrected JumpFix", jumpFix)

        # accel
        if (diff+fix) > 0.033 or (lastSpeed>1 and (diff+fix) > 0) :
            speed = round( 1+(diff+fix)*1.65, 2)
            speed = min(speed, 4.2)

        # decel
        elif (diff+fix) < -0.033 or (lastSpeed<1 and (diff+fix) < 0):
            speed = round( 1+ min(-0.04, diff+fix), 2)
            speed = max(speed, 0.1)

    player.speed(speed)
    lastSpeed = speed

    # LOG
    if doLog:
        if speed != 1.0:
            color1 = 'green'
            if abs(diff+fix) > 0.08: color1 = 'red'
            elif abs(diff+fix) > 0.04: color1 = 'yellow'

            color2 = 'white'
            if speed > 1: color2 = 'magenta'
            elif speed < 1: color2 = 'cyan'


            framedelta = math.trunc(diff*1000/30)
            color3 = 'green'
            if abs(framedelta) > 1: color3 = 'red'
            elif abs(framedelta) > 0: color3 = 'yellow'

            print(str(args[0]), end="\t")
            # print(str(clock), end="\t")
            # print(str(pos), end="\t")
            print("timedelay=" + colored(round(diff,2),color1), end="\t")
            print("framedelta=" + colored(framedelta,color3), end="\t")
            print("speed=" + colored(speed, color2) )

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
