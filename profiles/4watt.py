from core.engine import hplayer
from core.engine import network
import os, types, platform

# MACHINE
is_RPi = platform.machine().startswith('armv')

# NAME
playerName = network.get_hostname()

# PLAYER
player = hplayer.addplayer('mpv', '4watt')
player.loop(1)
player.doLog['events'] = True

# Interfaces
player.addInterface('kyre')


def yo(args):
	print ('/yo', args)
	player.getInterface('zyre').node.broadcast('/yeah', args, 3000)

player.on(['/yo'], yo)

player.on(['/yeah'], lambda args: print("YEAH", args))


# RUN
hplayer.setBasePath(["/data/media"])        	# Media base path
hplayer.run()                               # TODO: non blocking
