from core.engine import hplayer
from core.engine import network

# NAME
playerName = network.get_hostname()

# PLAYER
player = hplayer.addplayer('mpv', 'default')

# INTERFACES
player.addInterface('osc', 4000, 4001)
player.addInterface('http2', 8080)

## Example event: HTTP + GPIO events
# player.addInterface('http', 9090)
# player.addInterface('gpio', [20])
# player.on(['push1', 'gpio20'], lambda : player.play('media.mp4'))

# RUN
hplayer.setBasePath("/home/mgr/Videos")
hplayer.persistentSettings("/home/mgr/hplayer2.cfg")
hplayer.run()
