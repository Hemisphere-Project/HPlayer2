from time import sleep
from core.engine import hplayer

# PLAYER
player = hplayer.addplayer('mpv', 'dev-player')

# INTERFACES
player.addInterface('http2', 8080)

# RUN
hplayer.setBasePath(["/home/mgr/Videos/", "/home/mgr/Public/"])
hplayer.persistentSettings("/home/mgr/hplayer2-chrd.cfg")
hplayer.run()
