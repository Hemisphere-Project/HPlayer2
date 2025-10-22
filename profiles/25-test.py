from core.engine.hplayer import HPlayer2
from core.engine import network

# INIT HPLAYER
hplayer = HPlayer2(config=True)

# PLAYER
player = hplayer.addPlayer('mpv', 'player')

# Interfaces
hplayer.addInterface('http2', 8080, {'playlist': False, 'loop': False})
hplayer.addInterface('nowde', player)


# HTTP2 Logs
@hplayer.on('player.*')
@hplayer.on('nowde.*')
def http2_logs(ev, *args):
	if len(args) and args[0] == 'time': return
	hplayer.interface('http2').send('logs', [ev]+list(args))

# RUN
hplayer.run()
