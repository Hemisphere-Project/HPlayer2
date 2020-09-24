from core.engine.hplayer import HPlayer2


# INIT HPLAYER
hplayer = HPlayer2('/data')


# INTERFACES
hplayer.addInterface('keyboard')
hplayer.addInterface('mqtt', '10.0.0.1')


@hplayer.on('keyboard.*')
def keyboard2MQTT(ev, *args):
    ev = ev.split('.')[-1]

    # mem
    if ev[6].isnumeric() and ev[8:] == 'down':
        hplayer.interface('mqtt').send('k32/all/leds/mem', ev[6])
    
    # blackout
    elif ev == 'KEY_KPENTER-down':
        hplayer.interface('mqtt').send('k32/all/leds/stop')

    # + modulators
    elif ev == 'KEY_KPPLUS-down' or ev == 'KEY_KPPLUS-hold':
        hplayer.interface('mqtt').send('k32/all/leds/modi/0/faster')

    # - modulators
    elif ev == 'KEY_KPMINUS-down' or ev == 'KEY_KPMINUS-hold':
        hplayer.interface('mqtt').send('k32/all/leds/modi/0/slower')


# RUN
hplayer.run()                               						# TODO: non blocking
