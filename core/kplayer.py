from engine import hplayer

if __name__ == '__main__':

    # PLAYER
    player = hplayer.addplayer('mpv', 'kplayer')

    # Interfaces
    player.addInterface('kmsg')

    # RUN
    hplayer.setBasePath("/home/mgr/Videos/")
    hplayer.run()
