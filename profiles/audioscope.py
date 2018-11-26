from core.engine import hplayer
from core.engine import network


# PLAYER
player = hplayer.addplayer('mpv', 'audioscope')
player.loop(1)
player.log['events'] = True

# Interfaces
player.addInterface('osc', 1222, 3737)
player.addInterface('http', 8080)
player.addInterface('nfc', 4, 5)

# HTTP + GPIO events
player.on(['nfc-card'], lambda args: player.play(args[0]['uid']+"-*.*"))
player.on(['nfc-nocard'], player.stop)


# RUN
hplayer.setBasePath(["/media/usb"])
hplayer.run()
