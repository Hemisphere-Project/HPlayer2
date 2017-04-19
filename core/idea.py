from engine import hplayer

if __name__ == '__main__':

    # PLAYER
    player = hplayer.addplayer('mpv', 'myPlayer')

    # Interfaces
    player.addInterface('osc', [4000, 4001])

    # RUN
    hplayer.setBasePath("/home/pi/media/")
    hplayer.run()                              
