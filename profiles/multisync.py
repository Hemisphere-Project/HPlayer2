from core.engine.hplayer import HPlayer2
from core.engine import network

import os, sys, types, platform

# DIRECTORY / FILE
profilename = os.path.basename(__file__).split('.')[0]
base_path = ['/data/sync/'+profilename, '/data/usb']

# INIT HPLAYER
hplayer = HPlayer2(base_path, "/data/hplayer2-"+profilename+".cfg")

# PLAYERS
player 	= hplayer.addPlayer('mpv','mpv')
# midi 	= hplayer.addPlayer('midi','midi')

# Interfaces
hplayer.addInterface('zyre')
hplayer.addInterface('http2', 8080)
# hplayer.addInterface('http', 8037)
# hplayer.addInterface('keyboard')
hplayer.addInterface('teleco')



# MASTER / SLAVE sequencer
iamLeader = False

# Broadcast Order on OSC/Zyre to other Pi's
#
def broadcast(path, *args):
	print(path, list(args))
	if path.startswith('play'):
		hplayer.interface('zyre').node.broadcast(path, list(args), 200)   ## WARNING LATENCY !!
	else:
		hplayer.interface('zyre').node.broadcast(path, list(args))

# Detect if i am zyre Leader
@hplayer.on('zyre.event')
def leadSequencer(ev, *data):
	global iamLeader
	iamLeader = (data[0]['from'] == 'self')

# Receive a sequence command -> do Play !
@hplayer.on('zyre.playdir')
def doPlay(ev, *data):
	print(data)
	s = data[0]
	hplayer.playlist.play( hplayer.files.selectDir(s)+'/'+HPlayer2.name()+'*' )

# Receive an exit command -> last seq
@hplayer.on('zyre.end')
def doExit(ev, *args):
	hplayer.playlist.play( hplayer.files.selectDir(2)+'/'+HPlayer2.name()+'*' )


# Media end: next dir / or loop (based on directory name)
@hplayer.on('playlist.end')
# @midi.on('stop')
def endSequence(ev, *args):
	if not iamLeader:  
		return
	if 'loop' in hplayer.files.currentDir():
		broadcast('playdir', hplayer.files.currentIndex())
	else:
		broadcast('playdir', hplayer.files.nextIndex())


# Teleco
#
@hplayer.on('teleco.play')
@hplayer.on('http2.playindex')
def telecoplay(ev, *args):
    broadcast('playdir', hplayer.files.currentIndex())

# Keyboard
#
# @hplayer.on('keyboard.*')
# def keypress(ev, *args):
# 	if ev == 'keyboard.KEY_KP0-down': broadcast('playdir', 0)
    	
# hplayer.on('keyboard.KEY_KP1-down', 		lambda: broadcast('playdir', 1))
# hplayer.on('keyboard.KEY_KP2-down', 		lambda: broadcast('playdir', 2))
# hplayer.on('keyboard.KEY_KP3-down', 		lambda: broadcast('playdir', 3))
# hplayer.on('keyboard.KEY_KP4-down', 		lambda: broadcast('playdir', 4))
# hplayer.on('keyboard.KEY_KP5-down', 		lambda: broadcast('playdir', 5))
# hplayer.on('keyboard.KEY_KP6-down', 		lambda: broadcast('playdir', 6))
# hplayer.on('keyboard.KEY_KP7-down', 		lambda: broadcast('playdir', 7))
# hplayer.on('keyboard.KEY_KP8-down', 		lambda: broadcast('playdir', 8))
# hplayer.on('keyboard.KEY_KP9-down', 		lambda: broadcast('playdir', 9))
# hplayer.on('keyboard.KEY_KPENTER-down',     lambda: broadcast('stop'))
# hplayer.on('keyboard.KEY_KPDOT-down',       lambda: broadcast('end'))

# hplayer.on('keyboard.KEY_KPPLUS-down', 		lambda: broadcast('volume', hplayer.settings.get('volume')+1))
# hplayer.on('keyboard.KEY_KPPLUS-hold', 		lambda: broadcast('volume', hplayer.settings.get('volume')+1))
# hplayer.on('keyboard.KEY_KPMINUS-down', 	lambda: broadcast('volume', hplayer.settings.get('volume')-1))	
# hplayer.on('keyboard.KEY_KPMINUS-hold', 	lambda: broadcast('volume', hplayer.settings.get('volume')-1))	




# RUN
hplayer.run()                               						# TODO: non blocking
