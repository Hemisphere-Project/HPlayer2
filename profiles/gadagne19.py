from core.engine import hplayer

# PLAYER
player = hplayer.addplayer('mpv', 'gadagne')
player.doLog['events'] = True
player.doLog['cmds'] = True

# Interfaces
player.addInterface('http', 8080)
player.addInterface('http2', 8088)
if hplayer.isRPi():
    player.addInterface('gpio', [20,21,16])

# Remove default stop at "end-playlist" (or it prevent the next play !)
player.unbind('end-playlist', player.stop)

# DEFAULT File
player.on(['player-ready', 'end-playlist'], lambda: player.play("0_*.*"))

# HTTP + GPIO events
player.on(['push1', 'gpio21'], lambda: player.play("1_*.*"))
player.on(['push2', 'gpio20'], lambda: player.play("2_*.*"))
player.on(['push3', 'gpio16'], lambda: player.play("3_*.*"))


# PATH
hplayer.setBasePath("/home/mgr/Videos/test")
hplayer.persistentSettings("/home/mgr/Videos/gadagne/hplayer2-gadagne19.cfg")

# DISABLE automations
player.loop(False)
player.autoplay(False)
player.clear()

# RUN
hplayer.run()
