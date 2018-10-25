from time import sleep
from core.engine import hplayer

# PLAYER
player = hplayer.addplayer('mpv', 'looper-chrd')

# INTERFACES
player.addInterface('http2', 80)

# RUN
hplayer.setBasePath(["/data/media"])
hplayer.persistentSettings("/data/hplayer2-chrd.cfg")
hplayer.run()
