
#import subprocess, os
#black = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'black.png')
#image = subprocess.Popen(["/usr/bin/fbi", "-d", "/dev/fb0", "--noverbose", "-a", black])

import sys
from core.engine import hplayer

# print ASCII art of HPLAYER2

print("\
\n\
██╗  ██╗██████╗ ██╗      █████╗ ██╗   ██╗███████╗██████╗ ██████╗ \n\
██║  ██║██╔══██╗██║     ██╔══██╗╚██╗ ██╔╝██╔════╝██╔══██╗╚════██╗ \n\
███████║██████╔╝██║     ███████║ ╚████╔╝ █████╗  ██████╔╝ █████╔╝ \n\
██╔══██║██╔═══╝ ██║     ██╔══██║  ╚██╔╝  ██╔══╝  ██╔══██╗██╔═══╝  \n\
██║  ██║██║     ███████╗██║  ██║   ██║   ███████╗██║  ██║███████╗ \n\
╚═╝  ╚═╝╚═╝     ╚══════╝╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═╝╚══════╝ \n\
\n")

profile = 'looper'
if len(sys.argv) > 1:
    profile = sys.argv[1]

__import__("profiles."+profile)
sys.exit(0)
try:
    print ("HPlayer2: loading "+profile+" profile...\n")
    __import__("profiles."+profile)
except ImportError:
    print ("HPlayer2: profile not found\n")
    sys.exit(1)
