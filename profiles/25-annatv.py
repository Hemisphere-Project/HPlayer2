from core.engine.hplayer import HPlayer2
from core.engine import network

# INIT HPLAYER
hplayer = HPlayer2(config=True)

# PLAYER
player = hplayer.addPlayer('mpv', 'player')
player.imagetime(15)

player.doLog['events'] = True
player.doLog['cmds'] = True


# Interfaces
hplayer.addInterface('http2', 8080, {'playlist': False, 'loop': False, 'mute': True})
hplayer.addInterface('nowde', player)


# HTTP2 Logs
@hplayer.on('player.*')
@hplayer.on('sampler.*')
@hplayer.on('gpio.*')
@hplayer.on('serial.*')
def http2_logs(ev, *args):
	if ev.startswith('gpio') and ev.find('-') == -1: return 
	if len(args) and args[0] == 'time': return
	hplayer.interface('http2').send('logs', [ev]+list(args))

# RUN
hplayer.run()
