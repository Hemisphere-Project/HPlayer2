from core.engine import hplayer

# PLAYER
player = hplayer.addplayer('mpv', 'myPlayer')

# Interfaces
player.addInterface('osc', [4000, 4001])
player.addInterface('http', [8037])
# player.addInterface('gpio', [16,19,20,21,26])


# RUN
hplayer.setBasePath("/mnt/usb/")
hplayer.run()                               # TODO: non blocking
