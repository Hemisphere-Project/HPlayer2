from time import sleep
from core.engine import hplayer

# PLAYER
player = hplayer.addplayer('mpv', 'looper')

# INTERFACES
player.addInterface('http2', 8080)

# INTERNAL events
player.on(['player-ready'], lambda : player.play('*'))

# RUN
hplayer.setBasePath(["/data/chrd"])
hplayer.persistentSettings("/data/hplayer2-chrd.cfg")
hplayer.run()
