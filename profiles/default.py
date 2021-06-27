from core.engine.hplayer import HPlayer2        # Import base HPlayer2 class 


# HPLAYER2
hplayer = HPlayer2(                             # Initialize HPlayer2 object
        basepath=['/data/usb', '/data/media'],  # basepath is a list of base directories for media collection search. 
        settingspath="/data/hplayer2.cfg")      # settingspath is the path to persistent settings file. If ommited, no settings (like volume) will be kept between restarts.


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




# RUN
hplayer.run()                                   # Run everything 						

