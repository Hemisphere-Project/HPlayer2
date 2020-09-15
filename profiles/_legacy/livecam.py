from core.engine.hplayer import HPlayer2
from core.engine import network

import os, sys, types, platform

profilename = os.path.basename(__file__).split('.')[0]

# DIRECTORY / FILE
base_path = '/data/media/'

# INIT HPLAYER
hplayer = HPlayer2(base_path)

# PLAYERS
player 	= hplayer.addPlayer('mpv','mpv')

# Interfaces
hplayer.addInterface('osc', 4000, 4000)

# RUN
hplayer.run()                               						# TODO: non blocking
