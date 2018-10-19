from core.engine import hplayer

# PLAYER
player = hplayer.addplayer('mpv', 'myPlayer')

# Interfaces
player.addInterface('osc', 4000, 4001)
player.addInterface('http2', 8080)
# player.addInterface('gpio', [20])

# Example event: HTTP + GPIO events
# player.on(['push1', 'gpio20'], lambda : player.play('media.mp4'))

# RUN
hplayer.setBasePath("/home/mgr/Videos")
hplayer.persistentSettings("/home/mgr/hplayer2.cfg")
hplayer.run()
