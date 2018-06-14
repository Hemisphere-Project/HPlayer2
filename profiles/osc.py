from core.engine import hplayer

# PLAYER
player = hplayer.addplayer('mpv', 'myPlayer')

# Interfaces
player.addInterface('osc', [4000, 4001])

# RUN
hplayer.setBasePath("/home/pi/media/")
hplayer.run()
