# HPlayer2
HPlayer2 is a modular media player designed to allow multiple ways of control, over multiple platform.

It is build in a modular way: you can choose the player engine (mpv, vlc, omxplayer, ...),  
i/o interfaces (osc, http, rfid, ble, gpio, ...) and patch everything up.

HPlayer2 is focused on Raspberry Pi, but is based on python code wrapping 3rd parties engines and libraries, so as long as those 3rd parties components are supported on other platform, HPlayer2 should run on it !

HPlayer2 is under development, some features might not be fully available or sometimes broken, feel free to ask for help and open issues, i'll do my best to cover it. Pull requests are also welcomed !

## Media engine
Hplayer2 abstracts the concept of player (media list, play, pause, stop, volume, position, ...),
and then bind to an existing player engine.

On Raspberry Pi, i only managed to use 3 engines with Hardware acceleration on H.264 decoding:
 - omxplayer: the original HPlayer was based on via ofxOMXPlayer, but using OF on Pi was a bit tricky at the time
 - vlc: works great, but was tricky to compile on RPi when i tried it couple years ago
 - mpv: used to have a great build script, works very well and offers ipc interface to communicate with

The goal of HPlayer2 is to offer the choice between those 3 engines, but for now only **mpv** is fully supported.

## Install
HPlayer2 is a python program, with several "modular" dependencies, depending on which component you will be using.  
The core component you need to install is of course the media engine.
For now, only **mpv** is supported, so you should install it, but the **mpv** package in your distro repository might not be compiled with HW video decoding, so it might be necessary to build it yourself with this specific options enabled.

There is two scripts to help you install everything needed:

**scripts/install_dependencies.sh** that should cover most of the dependencies installation. 
This script supports **arch** and **xbian** (raspbian/debian/ubuntu)  
On Raspberry Pi, i recommand using arch since boot up is faster, but it's up to you !
The script might miss some recent dependencies (i sometime forget to update this script for brand new features).

**scripts/install_mpv.sh** tries to detect if a pre-compiled version of MPV is available for your platform.
If not, it tries to re-compile MPV with HW acceleration for RaspberryPi. 

Feel free to dive into both scripts and tweak it for your needs.
If you want help make install script more universal, please submit PR !

On your freshly configured Raspberry Pi:

    cd ~
    git clone https://github.com/Hemisphere-Project/HPlayer2.git
    cd HPlayer2/scripts
    sudo ./install_dependencies.sh
    sudo ./install_mpv.sh
    cd ..

You should examine those scripts to understand what they do.
You could run each part on your own instead of running the whole script blindly,  
it will help in case it is broken (it can be !).

## Run
Since HPlayer2 is modular, the concept is to run HPlayer2 against a specific **profile**.
This **profile** links i/o interfaces to the media engine.  
There is a default profile provided, and several example based on projects where i use HPlayer2.

To start, go to HPlayer2 directory, and run `./hplayer2 profile`  
where *profile* is the name of a file in the **profiles** subdirectory (without the .py)

for exemple you can run `./hplayer2 bloffique`   
which will start HPlayer with the profile located in **profiles/bloffique.py**

if you omit the profile and simply run `./hplayer2`  
it will use the default profile located in **profiles/default.py**

To create a custom profile for your project, 
you can create a new file like **profiles/your-project.py**
To run it: `./hplayer2 your-project`


## Patch a profile
The idea here is for you to program you own profile !  
(or to use an existing one if it feats your needs..)

Start reading the files in **profiles/** to see examples on how profiles are made.  
It's very simplified and *patching* oriented: an interface event can be plugged to a player action and vice-versa.

The best starting point is to read the default profile in **profiles/default.py**

The idea in a profile is:
 - create a player
 - attach interfaces modules (OSC, HTTP, RFID, GPIO, ...)
 - patch events from interfaces to action on the player (NB: some events are already patched automatically)
 - run


## Interfaces
A more complete documentation regarding the capabilities and the use of the different interface modules will be provided in the future (PR and help are welcome!).  
Interfaces are available without the need of explicit inclusion, from directory **core/interfaces/**

Please check the profiles examples to see how to use those interfaces.

Available interfaces:
 - GPIO: allows patching RPi gpio event to player action
 - OSC: patching OSC message to player actions to control it from TouchOSC / MaxMSP / etc...
 - HTTP: bootstrap a basic HTTP server to enable network basic API
 - HTTP2: a nice web interface (responsive & websocket enabled) to setup an control HPlayer2
 - Keyboard: usb keyboard, numpad or infrared remotes like [this one](https://goo.gl/sz7rie)
 - Keypad: interface LCD+Keypad RPi shield like [this one](https://www.adafruit.com/product/1110)
 - NFC: interface RFID/NFC tag reader based on PN532 like [this one](https://www.adafruit.com/product/364)


## CREDITS
HPlayer2 is developed by Thomas BOHL for [Hemisphere](https://www.hemisphere-project.com/) and [KXKM](https://kxkm.net/)

HPlayer2 is build on top of MPV player, liblo, Adafruit libs, ZeroMQ and more.. thanks to all those open developers !
