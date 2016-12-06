# HPlayer2
OSC controllable, GPU accelerated, ALSA compatible VideoPlayer for Raspberry Pi and more

HPlayer2 is build around a python modular architecture.
You can load several interfaces: OSC, HTTP, GPIO, .. and bind events to player actions.

By default HPlayer2 offers generic bindings to control the player,
but you can easily program yours.

In early development .. stay tuned !


## INSTALL

Download the project, install dependencies, build mpv for your plateform

xBian version (Ubuntu, Debian, Raspbian):

```
wget -O - https://raw.githubusercontent.com/Hemisphere-Project/HPlayer2/master/scripts/remote_install.sh | bash
```

Beware that it will take some time, especially on Raspberry Pi, since MPV is recompiled on spot.


## RUN

Go the HPlayer2 directory and run it:

```
./hplayer2
```

For now, it might not work out of the box.
You can tweak the behaviour by editing python/hplayer2.py

We will provide a ready to use build soon, with json configs files (both default and overwritted examples).

Please use Github Issue system to ask question, provide feedback or improvments ideas.
Thanks !


## CREDITS

HPlayer2 is build on top of MPV Player, liblo, cherrypy and more..
Thanks to all those developer teams !
