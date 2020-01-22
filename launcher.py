
#import subprocess, os
#black = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'black.png')
#image = subprocess.Popen(["/usr/bin/fbi", "-d", "/dev/fb0", "--noverbose", "-a", black])

import sys
from core.engine import hplayer

profile = 'default'
if len(sys.argv) > 1:
    profile = sys.argv[1]
print ("HPlayer2: loading "+profile+" profile...\n")

__import__("profiles."+profile)
