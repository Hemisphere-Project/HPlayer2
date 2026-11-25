#
# 27-kxkm — the KXKM fleet on RastaOS 7.5 (hplayer2#t-107)
#
# A 7.5 card behaves like today's 6.x player (branch sacvp-kernel4-2025, profiles/sacvp.py):
# the USB numeric keypad drives the Régie, an M5 on USB serial, OSC in 1222 / out 3737, the
# rpifade overlay, and at boot it waits for a cue (volume 100, loop 1, nothing plays).
# From 25-kxkm it takes what 7.5 adds: /boot/hplayer2.conf ([sync] iface binds the mesh), the
# etendard mode, group.json, and the LPD8 sampler pad.
#
# Show folder: /data/sync/27-kxkm, from this file's name like both parents. The Régie's
# project.json is read there, so casa copies sacvp/ into it before a 7.5 card boots.
#
from core.engine.hplayer import HPlayer2
from core.engine.playlist import Playlist
from core.engine import network
from core.engine import bootconf

import os
import json, glob

try:
    from pythonosc import udp_client
except ImportError:  # pragma: no cover - optional dependency
    udp_client = None


# DIRECTORY / FILE
profilename = os.path.basename(__file__).split('.')[0]
projectfolder = os.path.join('/data/sync', profilename)

devicename = network.get_hostname()
devicefolder = os.path.join('/data/sync/solo', devicename)

# INIT HPLAYER (settings on /data: the root is read-only)
hplayer = HPlayer2(['/data/usb', projectfolder, devicefolder], '/data/hplayer2-'+profilename+'.cfg')

# ATTACHED ETENDARD: get ETENDARD from etendard.json
myETEND = None
try:
    with open(os.path.join(projectfolder, 'etendard.json')) as json_file:
        data = json.load(json_file)
        if devicename in data:
            myETEND = data[devicename]
            hplayer.log('attached to ETENDARD', myETEND)
except: pass

# ATTACHED GROUP: get GROUP from group.json
myGROUP = []
try:
    with open(os.path.join(projectfolder, 'group.json')) as json_file:
        data = json.load(json_file)
        for k in data:
            if devicename in data[k]:
                myGROUP = data[k]
                hplayer.log('attached to GROUP', myGROUP)
except: pass

# /boot/hplayer2.conf (hplayer2#t-101): [sync] iface binds the Zyre mesh; absent = as before
# (wint for an etendard, Zyre's own choice for HDMI). Every kxkm player is a mesh peer: a role,
# a wall, a schedule or a keypad/teleco2/nowde switch in the conf is reported, never obeyed.
# (The USB numeric keypad below is the `keyboard` interface, not the conf's `keypad`.)
BOOTCONF = bootconf.load()
BOOTCONF.schedule(False, runs=False)
for _i in ('keypad', 'teleco2', 'nowde'):
    BOOTCONF.interface(_i, False, runs=False)

# SAMPLER PAD (HDMI players only)
sampler = None
playlistSampler1 = None
playlistSampler2 = None

# PLAYERS
# ETENDARD
if myETEND:
    video = hplayer.addPlayer('videonet', 'video')
    video.setSize(*myETEND['size'], myETEND['snake'], myETEND['vflip'], myETEND['hflip'])
    video.setIP(myETEND['ip'])
    hplayer.log('mode VIDEO4ARTNET')
    # Ethernet Zyre
    hplayer.addInterface('zyre', BOOTCONF.mesh_iface('wint'))

# HDMI
else:
    video = hplayer.addPlayer('mpv', 'video')
    stream = hplayer.addPlayer('mpvstream', 'stream')
    hplayer.log('mode HDMI')

    # Any Zyre
    hplayer.addInterface('zyre', BOOTCONF.mesh_iface(None))

    # Fade overlay (6.x: on). A card whose GL/DRM libraries are missing plays on, without fade:
    # a profile that raises at import crash-loops the launcher.
    if hplayer.isRPi():
        try:
            video.addOverlay('rpifade')
        except Exception as err:
            hplayer.log('rpifade overlay not available, no fade:', err)

    # Sampler Pad
    sampler = hplayer.addSampler('jp', 'audio', 2)

    # Playlist Sampler 1 from ZZ_AUDIOLOOP => loops
    playlistSampler1 = Playlist(hplayer, 'Playlist-sampler')
    filelist = hplayer.files.listFiles('ZZ_AUDIOLOOP/*')
    filelist = [f for f in filelist if sampler.playerAt(0).validExt(f)]
    playlistSampler1.load(filelist)

    # Playlist Sampler 2 from ZZ_AUDIOSHOT => one shot
    playlistSampler2 = Playlist(hplayer, 'Playlist-sampler')
    filelist = hplayer.files.listFiles('ZZ_AUDIOSHOT/*')
    filelist = [f for f in filelist if sampler.playerAt(1).validExt(f)]
    playlistSampler2.load(filelist)


# INTERFACES
hplayer.addInterface('keyboard')                    # USB numeric keypad -> Régie (below)
hplayer.addInterface('osc', 1222, 3737)             # out: broadcast address, port 3737
hplayer.addInterface('serial', 'M5', 10)
hplayer.addInterface('midictrl', 'LPD8', 10)
hplayer.addInterface('mqtt', '10.0.0.2')
hplayer.addInterface('http2', 8080)
hplayer.addInterface('teleco')
hplayer.addInterface('regie', 9111, projectfolder)

# The LPD8 lights go to a local hartnet on 9000 (25-kxkm), not to the show's OSC out 3737
hartnet = udp_client.SimpleUDPClient('127.0.0.1', 9000) if udp_client else None

def hartnetSend(path, *args):
    if hartnet:
        hartnet.send_message(path, list(args))


#
# SYNC PLAY
#

# Broadcast Order on Zyre to other Pi's: play with 500 ms latency, the rest at once (6.x)
#
def broadcast(path, *args):
    if path.startswith('play'):
        hplayer.interface('zyre').node.broadcast(path, list(args), 500)   ## WARNING LATENCY !!
    else:
        hplayer.interface('zyre').node.broadcast(path, list(args))

# Cast to group on Zyre
def groupcast(path, *args):
    delay = 500 if path.startswith('play') else 0
    if len(myGROUP) > 0:
        for group in myGROUP:
            hplayer.interface('zyre').node.shout(group, path, list(args), delay)   ## WARNING LATENCY !!
    else:
        hplayer.interface('zyre').node.tomyself(path, list(args))


#
# MIDI CTRL (LPD8 sampler pad)
#
volumeLoop = 100
volumeShot = 100

LOOP_NOTES  = {40: 1, 41: 2, 42: 3, 43: 4, 36: 5, 37: 6, 38: 7}        # note -> light (= loop index+1)
SHOT_CC     = {16: 0, 17: 1, 18: 2, 19: 3, 12: 4, 13: 5, 14: 6}        # cc -> one-shot index
LIGHT_PC    = {4: 1, 5: 2, 6: 3, 7: 4, 0: 5, 1: 6, 2: 7}               # program -> light

@hplayer.on('midictrl.noteon')
@hplayer.on('midictrl.cc')
@hplayer.on('midictrl.pc')
def midiEvent(ev, *args):
    if not playlistSampler1: return
    if not playlistSampler2: return
    global volumeLoop, volumeShot
    track = None
    light = None

    if ev == 'midictrl.noteon':
        value = args[0]['note']
        if value in LOOP_NOTES:
            light = LOOP_NOTES[value]
            track = playlistSampler1.trackAtIndex(light-1)
        elif value == 39:
            track = 'stop'
            light = 'stop'

        if track == 'stop':
            sampler.stop()
        elif track:
            sampler.play(track, oneloop=True, index=0)

        if light == 'stop': hartnetSend('/hartnet/stop')
        elif light: hartnetSend('/hartnet/play', light)

    if ev == 'midictrl.cc':
        value = args[0]['control']

        if value in SHOT_CC: track = playlistSampler2.trackAtIndex(SHOT_CC[value])
        elif value == 15: track = 'stop'

        # volumes
        elif value == 70:
            hplayer.emit('volume', args[0]['value']*100/127)           # video volume
        elif value == 73:
            volumeLoop = args[0]['value']*100/127
            sampler.playerAt(0)._applyVolume(volumeLoop)    # sampler0 volume
        elif value == 77:
            volumeShot = args[0]['value']*100/127
            sampler.playerAt(1)._applyVolume(volumeShot)    # sampler1 volume

        # play sampler shot
        if track == 'stop':
            sampler.stop()
        elif track:
            sampler.play(track, oneloop=False, index=1)

    if ev == 'midictrl.pc':
        value = args[0]['program']
        if value in LIGHT_PC: light = LIGHT_PC[value]
        elif value == 3: light = 'stop'

        if light == 'stop': hartnetSend('/hartnet/stop')
        elif light: hartnetSend('/hartnet/play', light)


# SMS
#
sms_counter = 0
peers_counter_dispatch = 0
for f in glob.glob('/tmp/txt2img*'): os.remove(f)   # clear old msgs

# SMS DISPATCHER (only CASA) MQTT -> ZYRE
@hplayer.on('mqtt.textdispatch')
def textdispatchM(ev, *args):
    zyre = hplayer.interface('zyre')
    peersList = list(zyre.peersList())
    peersList.remove(zyre.node.uuid)
    if len(peersList) == 0: return

    global peers_counter_dispatch
    peers_counter_dispatch = (peers_counter_dispatch+1)%len(peersList)
    hplayer.interface('zyre').node.whisper(peersList[peers_counter_dispatch], 'text', args)


# SMS TEXT ALL (only CASA) MQTT -> ZYRE
@hplayer.on('mqtt.textall')
def textallM(ev, *args):
    hplayer.interface('zyre').node.broadcast('textall', args)


# SMS STOP ALL (only CASA) MQTT -> ZYRE
@hplayer.on('mqtt.textstop')
def textstopM(ev, *args):
    hplayer.interface('zyre').node.broadcast('textstop')


# SMS DISPLAY
@hplayer.on('zyre.text')
def text(ev, *args):
    global sms_counter

    args = list(args[0])
    if len(args) == 1: args.append(None)            #encoding
    if len(args) == 2: args.append(sms_counter)     #suffix

    file = hplayer.imgen.txt2img(*args)

    hplayer.settings.set('loop', 2)
    hplayer.playlist.load(glob.glob('/tmp/txt2img*'))

    i = hplayer.playlist.findIndex(file)
    if i > -1: hplayer.playlist.remove(i)
    hplayer.playlist.randomize()
    hplayer.playlist.add(file)
    hplayer.playlist.last()

    sms_counter = (sms_counter+1)%10


@hplayer.on('zyre.textstop')
def textstop(ev, *args):
    hplayer.interface(ev.split('.')[0]).emit('stop')
    global sms_counter
    sms_counter = 0
    os.system('rm -Rf /tmp/txt2img*')


@hplayer.on('zyre.textall')
def textclear(ev, *args):
    textstop(ev)
    msg = args[0]
    if len(msg) >= 1 and len(msg[0]) >= 1:
        msg[0] = msg[0].replace("+33", "0")
        if msg[0].startswith("0") and len(msg[0]) == 10:
            msg[0] = ' '.join(msg[0][i:i+2] for i in range(0, len(msg[0]), 2))
        text(None, msg)


# PIR
#
@hplayer.on('*.pir')
def pir(ev, *args):
    if len(args) > 0:
        if args[0] == 'ON':
             if not video.isPlaying():
                hplayer.playlist.playindex(0)
             hplayer.settings.set('loop', 2)
        elif args[0] == 'OFF':
             if video.isPlaying():
                hplayer.settings.set('loop', 0)


# KEYBOARD: the USB numeric keypad pilots the Régie (6.x)
#   digit = play that Régie sequence of the current scene · dot held + digit = select a scene
#   Enter = stop all players · + / - = volume of all players
#
dotHold = False

@hplayer.on('keyboard.*')
def keyboard(ev, *args):
    global dotHold

    base, key = ev.split("keyboard.KEY_")
    if not key: return

    key, mode = key.split("-")
    if key.startswith('KP'): key = key[2:]

    # 0 -> 9
    if key.isdigit() and mode == 'down':
        numk = int(key)
        if dotHold:
            # select folder (locally only)
            hplayer.files.selectDir(numk)

        else:
            # play sequence regie
            hplayer.interface('regie').playseq(hplayer.files.currentIndex(), numk-1)

    elif key == 'ENTER' and mode == 'down':
        broadcast('stop')

    elif key == 'DOT':
        dotHold = (mode != 'up')

    elif key == 'NUMLOCK' and mode == 'down': pass
    elif key == 'SLASH' and mode == 'down': pass
    elif key == 'ASTERISK' and mode == 'down': pass
    elif key == 'BACKSPACE' and mode == 'down': pass

    # volume
    elif key == 'PLUS' and (mode == 'down' or mode == 'hold'):
        broadcast('volume', hplayer.settings.get('volume')+1)
    elif key == 'MINUS' and (mode == 'down' or mode == 'hold'):
        broadcast('volume', hplayer.settings.get('volume')-1)


#
# RUN
#

# boot: volume 100, loop 1, and wait for a cue (6.x) — no autoplay, no scaler, no brightness
@hplayer.on('app-run')
def init(ev, *args):
    hplayer.settings.set('volume', 100)
    hplayer.settings.set('loop', 1)


# RUN
hplayer.run()
