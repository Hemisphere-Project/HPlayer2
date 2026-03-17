from core.engine.hplayer import HPlayer2
from threading import Timer
import os, re

# INIT HPLAYER
hplayer = HPlayer2('/data/usb', '/data/hplayer2-26-bandit.cfg')

# PLAYER
player = hplayer.addPlayer('mpv', 'player')

# INTERFACES
hplayer.addInterface('http', 8080)          # simple HTTP: /trig will emit 'http.trig'
hplayer.addInterface('http2', 80)           # web UI
if hplayer.isRPi():
    gpio = hplayer.addInterface('gpio', [16], 200, 0, 'PUP')   # GPIO16 input pullup


# STATE
triggerArmed = False     # armed after 0_* starts playing
pulseTimer = None        # timer for GPIO20 HIGH pulse
retryTimer = None        # timer for retrying when no media found
cachedWaiting = None     # resolved path to first 0_* file
cachedTriggered = None   # resolved path to first 1_* file


# --- helpers ---

def cancelRetry():
    global retryTimer
    if retryTimer:
        retryTimer.cancel()
        retryTimer = None


def scanMedia():
    """Scan USB for first 0_* and 1_* files, cache results"""
    global cachedWaiting, cachedTriggered
    files = hplayer.files.listFiles('/')
    cachedWaiting = None
    cachedTriggered = None
    for f in sorted(files):
        name = os.path.basename(f)
        if cachedWaiting is None and re.match(r'^0_', name):
            cachedWaiting = f
        elif cachedTriggered is None and re.match(r'^1_', name):
            cachedTriggered = f
        if cachedWaiting and cachedTriggered:
            break
    hplayer.log(f"Scanned media: waiting={cachedWaiting}, triggered={cachedTriggered}")


def seamlessPlay(path):
    """Play file without stop command to avoid black frame between transitions"""
    player.update('isPaused', False)
    player.update('media', path)
    player.update('time', 0)
    player._mpv_send('{"command": ["loadfile", "' + path + '"]}')
    player._mpv_send('{ "command": ["set_property", "pause", false] }')


def playWaiting():
    """Play cached 0_* file in loop, arm trigger"""
    global triggerArmed
    cancelRetry()
    if not cachedWaiting:
        scanMedia()
    if cachedWaiting:
        player._applyOneLoop(True)
        seamlessPlay(cachedWaiting)
        triggerArmed = True
    else:
        # no media yet, will retry via nomedia-like mechanism
        global retryTimer
        hplayer.log("No waiting media found, retrying in 3s...")
        retryTimer = Timer(3.0, playWaiting)
        retryTimer.start()


def playTriggered():
    """Play cached 1_* file once (no loop), disarm trigger"""
    global triggerArmed
    triggerArmed = False
    if cachedTriggered:
        player._applyOneLoop(False)
        seamlessPlay(cachedTriggered)
    else:
        hplayer.log("No triggered media found")


def onTriggeredEnd():
    """Called when 1_* playlist finishes: pulse GPIO20 HIGH 3s then restart waiting"""
    global pulseTimer

    if hplayer.isRPi():
        gpio.set(20, True)         # GPIO20 HIGH

    playWaiting()
    pulseTimer = Timer(3.0, afterPulse)
    pulseTimer.start()


def afterPulse():
    """3s after triggered media ends: GPIO20 LOW, restart waiting loop, re-arm trigger"""
    global pulseTimer, triggerArmed
    pulseTimer = None
    if hplayer.isRPi():
        gpio.set(20, False)        # GPIO20 LOW
    triggerArmed = True


# --- events ---

# On startup → scan media, play 0_* and arm trigger
@hplayer.on('player.ready')
def onReady(ev, *args):
    global triggerArmed
    scanMedia()
    playWaiting()
    if hplayer.isRPi():
        gpio.set(20, False)        # GPIO20 LOW
    triggerArmed = True


# GPIO16 trigger (pulled to GND → '-on' with PUP)
@hplayer.on('gpio.16-on')
def gpioTrigger(ev, *args):
    if triggerArmed:
        playTriggered()

# HTTP /trig → simulates GPIO16 trigger
@hplayer.on('http.trig')
def httpTrigger(ev, *args):
    if triggerArmed:
        playTriggered()


# When 1_* nearend → pulse GPIO20 + restart waiting (seamless, no black)
@hplayer.on('player.nearend')
def onNearEnd(ev, *args):
    media = args[0] if args else ''
    if os.path.basename(media).startswith('1_'):
        onTriggeredEnd()


# Disable autoplay / force settings on load
@hplayer.on('settings.loading')
def onSettingsLoad(ev, *args):
    hplayer.settings.set('autoplay', False)


# USB replugged or content changed → rescan and restart if needed
@hplayer.on('files.dirlist-updated')
def onFilesChanged(ev, *args):
    cancelRetry()
    scanMedia()
    if not player.isPlaying():
        hplayer.log("Media changed, restarting...")
        playWaiting()


# RUN
hplayer.run()
