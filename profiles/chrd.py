from time import sleep
from core.engine import hplayer

# PLAYER
player = hplayer.addplayer('mpv', 'looper-chrd')

# INTERFACES
player.addInterface('http2', 8080)

# RUN
hplayer.setBasePath(["/data/chrd"])
hplayer.persistentSettings("/data/hplayer2-chrd.cfg")
hplayer.run()
