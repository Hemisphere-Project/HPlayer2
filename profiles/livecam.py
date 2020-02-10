from core.engine.hplayer import HPlayer2
from core.engine import network

import os, sys, types, platform

profilename = os.path.basename(__file__).split('.')[0]

# DIRECTORY / FILE
base_path = '/data/sync/'

# INIT HPLAYER
hplayer = HPlayer2(base_path)

# PLAYERS
player 	= hplayer.addPlayer('mpv','mpv')

# Interfaces
hplayer.addInterface('osc', 4000, 4000)

# RUN
hplayer.run()                               						# TODO: non blocking
