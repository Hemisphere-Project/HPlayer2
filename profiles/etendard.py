from core.engine.hplayer import HPlayer2
from core.engine import network
import os


# DIRECTORY / FILE
profilename = os.path.basename(__file__).split('.')[0]
projectfolder = os.path.join('/data/sync', profilename)

devicename = network.get_hostname()
devicefolder = os.path.join('/data/sync/solo', devicename)

base_path = ['/data/usb', projectfolder, devicefolder]


# INIT HPLAYER
hplayer = HPlayer2(base_path, "/data/hplayer2-"+profilename+".cfg")

# PLAYERS
video = hplayer.addPlayer('videonet', 'video')
video.setSize(36, 138)
video.setIP("2.12.0.2")

# LOAD ROOT FOLDER AS PLAYLIST
hplayer.playlist.load( hplayer.files.currentList() )


# INTERFACES
# hplayer.addInterface('zyre', 'wlan0') 
hplayer.addInterface('teleco')
# hplayer.addInterface('mqtt', '10.0.0.1')
# hplayer.addInterface('http2', 8080)


#
# RUN
#

# default volume
@video.on('ready')
def init(ev, *args):
    hplayer.settings.set('volume', 100)
    hplayer.settings.set('loop', -1)
            
# RUN
hplayer.run()                               						# TODO: non blocking
