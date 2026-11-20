from core.engine.hplayer import HPlayer2        # Import base HPlayer2 class 

MEDIA = ['/data/usb', '/data/media']            # media folders: a USB key, the card's own media partition


# HPLAYER2
hplayer = HPlayer2(                             # Initialize HPlayer2 object
        mediaPath=MEDIA,                        # media folders searched for the collection
        config="/data/hplayer2.cfg")            # persistent settings file (volume, ...) kept between restarts


# PLAYERS
player = hplayer.addPlayer('mpv', 'player')     # Create a media player based on mpv and named 'player'


# INTERFACES
hplayer.addInterface('keyboard')                # Enable Keyboard interface
hplayer.addInterface('osc', 4000, 4001)         # Enable OSC interface
hplayer.addInterface('http2', 8080)             # Enable HTTP2 interface (webpage to control the player)


# BIND specific keyboards events
@hplayer.on('keyboard.KEY_KPPLUS-down')         # Use decorator to catch event keyboard.KEY_KPPLUS-down -> emitted when + is pressed on keyboard
@hplayer.on('keyboard.KEY_KPPLUS-hold')         # Use decorator to catch event keyboard.KEY_KPPLUS-hold -> emitted repeatedly when + is hold pressed on keyboard
def volinc(ev, *args):                          # Define the function called by those decorators. Needs (ev, *args) where ev is the triggering event, and *args the list of optional arguments provided by the event
        hplayer.emit('volinc', 1)               # Emit a "volinc" event, which is already binded and will execute the volume incrementation.

@hplayer.on('keyboard.KEY_KPMINUS-down')         
@hplayer.on('keyboard.KEY_KPMINUS-hold')         
def voldec(ev, *args):                          
        hplayer.emit('voldec', 1)               




# PLAY ON BOOT: a card with no role file (RastaOS: hplayer2@auto -> 'default') plays its media in a loop,
# so a freshly burned card shows its clip (the image's 0_mire) on a screen with no laptop (hplayer2#t-104)
def playAll():
        hplayer.settings.set('loop', 2)                                 # loop all (a single file loops in mpv)
        hplayer.playlist.play(MEDIA)                                    # a missing folder lists nothing

@hplayer.on('app-run')                          # settings loaded, player ready -> play
def playOnBoot(ev, *args):
        playAll()

@hplayer.on('files.filelist-updated')           # media arrived on a card that booted with none (upload, USB key)
def playWhenMediaArrive(ev, *args):
        if hplayer.appRunning and hplayer.playlist.size() == 0 and not player.isPlaying():
                playAll()


# RUN
hplayer.run()                                   # Run everything 						

