from core.engine.hplayer import HPlayer2

tabHold = False
memDirectory = 0

# INIT HPLAYER
hplayer = HPlayer2('/data/sync')


# INTERFACES
hplayer.addInterface('keyboard')
hplayer.addInterface('mqtt', '10.0.0.1')


@hplayer.on('keyboard.*')
def keyboard2MQTT(ev, *args):
    ev = ev.split('.')[-1]

    # tab hold
    if ev.startswith('KEY_TAB'):
        global tabHold
        tabHold = not (ev == 'KEY_TAB-up')

    # mem / dir
    elif ev[6].isnumeric() and ev[8:] == 'down':
        global memDirectory
        if tabHold:
            memDirectory = int(ev[6])*10
        else:    
            hplayer.interface('mqtt').send('k32/all/leds/mem', str(memDirectory + int(ev[6])))

    # blackout
    elif ev == 'KEY_KPDOT-down':
        hplayer.interface('mqtt').send('k32/all/leds/stop')

    # + Master
    elif ev == 'KEY_BACKSPACE-down' or ev == 'KEY_BACKSPACE-hold':
        hplayer.interface('mqtt').send('k32/all/leds/modi/0/faster', None, 0)

    # - Master
    elif ev == 'KEY_KPASTERISK-down' or ev == 'KEY_KPASTERISK-hold':
        hplayer.interface('mqtt').send('k32/all/leds/modi/0/slower', None, 0)

    # + modulators
    elif ev == 'KEY_KPPLUS-down' or ev == 'KEY_KPPLUS-hold':
        hplayer.interface('mqtt').send('k32/all/leds/master/more', None, 0)

    # - modulators
    elif ev == 'KEY_KPMINUS-down' or ev == 'KEY_KPMINUS-hold':
        hplayer.interface('mqtt').send('k32/all/leds/master/less', None, 0)


# RUN
hplayer.run()                               						# TODO: non blocking
