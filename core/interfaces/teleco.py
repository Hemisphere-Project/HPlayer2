from .base import BaseInterface
from core.engine import network

import time, os
import serial
from serial.tools import list_ports
from threading import Timer

PAGE_EXIT       = -3
PAGE_WELCOME    = -2
PAGE_STATUS     = -1
PAGE_PLAYBACK   = 0
PAGE_MEDIA      = 1

PAGE_MAX        = 1

SCREEN_REFRESH  = 0.1


class TelecoInterface (BaseInterface):

    def  __init__(self, hplayer):
        super().__init__(hplayer, "Teleco")
        self.port = None
        self.serial = None
        self.filter = "Leonardo"
        self.nLines = 5

        self.activePage = PAGE_WELCOME

        self.dirPlayback = ''
        self.isFaded = False
        self._muteHolded = False

        self.microIndex = 0
        self.microOffset = 0
        self.microList = []

        self._buffer = [None]*self.nLines        
        self._hardClear = True
        self._delegate = None

        self.bind()
        self.clear()
        self.page(PAGE_WELCOME)
        self.refresh()
        self.timer(0.3, self.init)
        

    # SERIAL receiver THREAD
    def listen(self):

        firstTry = True

        while self.isRunning():

            # find port
            if not self.port:
                for dev in list_ports.grep(self.filter):
                    self.port = dev.device
                    break
                if not self.port:
                    if firstTry:
                        self.log("no device found.. retrying")
                        firstTry = False
                    # for p in list_ports.comports():
                    #     self.log(p)
                    time.sleep(3)
            
            # connect to serial
            elif not self.serial:
                try:
                    self.serial = serial.Serial(self.port, 115200, timeout=.1)
                    self.log("connected to", self.port, "!")
                    self.emit('ready')
                    self.clear()
                except:
                    self.log("connection failed on", self.port)
                    self.port = None
                    
            # read / write
            else:
                try:
                    data = self.serial.readline()[:-2].decode("utf-8") #the last bit gets rid of the new-line chars
                    if data:
                        self.emit(data)
                        # self.serial.write( ("2 1  "+data+"\n").encode() )
                    
                    say = None
                    if self._hardClear: 
                        say = '¤0'
                        self._hardClear = False

                    for i,l in enumerate(self._buffer):
                        if l['dirty']:
                            if not say: say = '¤'
                            else: say += '£'
                            say += str(i+1)
                            say += l['txt'].ljust(26, ' ')
                            l['dirty'] = False
                    
                    if say:
                        # self.log(say.encode())
                        say += '¤'
                        self.serial.write( (say).encode() )
                        # self.log(say)
                    
                    time.sleep(0.1)
                    self.refresh()

                except serial.SerialException:
                    self.log("broken link..")
                    self.serial = None
    
    # setTimeout: call after time
    def timer(self, timeout, fn, *args):
        if self._delegate and self._delegate.is_alive():
            self._delegate.cancel()
        self._delegate = Timer(2.0, fn, args)
        self._delegate.start()

    # clear display
    def clear(self):
        self._hardClear = True
        for i in range(self.nLines):
            self._buffer[i] = {'txt': '', 'dirty': True}

    # change line n
    def line(self, n, txt):
        if txt != self._buffer[n]['txt']:
            self._buffer[n]['txt'] = txt
            self._buffer[n]['dirty'] = True


    # change active page
    def page(self, p):
        self.activePage = p


    def init(self):
        self.page(PAGE_MEDIA)
        

    def refresh(self):

        if self.activePage == PAGE_WELCOME:

            self.line(0, '       ')
            self.line(1, '        KXKM')
            self.line(2, '^1     RPi-Player')
            self.line(3, '       ')
            self.line(4, '       ')

        elif self.activePage == PAGE_EXIT:

            self.line(0, '       ')
            self.line(1, '       ')
            self.line(2, '^0    ^2Ngoodbye !')
            self.line(3, '       ')
            self.line(4, '       ')

        elif self.activePage == PAGE_STATUS:

            net = network.get_essid('wlan0')
            if net: net += ' '+str(network.get_rssi('wlan0'))+'%'
            else:   net = 'NO-WIFI !'
            net = '  ^2P '+net

            z = self.hplayer.interface('zyre')
            if z: people = '  ^7C '+str(z.activeCount())
            else: people = '                   '

            self.line(0, '^1 STATUS')
            self.line(1, net)
            self.line(2, people)
            self.line(3, 'name: '+network.get_hostname())
            self.line(4, 'ip: '+network.get_ip('wlan0'))
        
        elif self.activePage == PAGE_PLAYBACK:

            player = self.hplayer.activePlayer()
            status = player.status()

            # Time & Media
            playstate = '                          '
            if player.isPlaying():
                if status['media']:
                    playstate = ' '+status['media'].split('/')[-1]      # leading space : prevent digit display error
            

            # MUTE & Time
            mutestate =  ' ^9JMUTE-VID  ' if self.isFaded else '             '
            if player.isPlaying():
                mutestate += ( str( round(status['time']) )+'/'+str( round(status['duration']) )+'"').rjust(8)


            # PLAY
            cmdline = '^5K'
            if player.isPlaying():
                cmdline = '^5D' if player.isPaused() else '^5E'
            cmdline += "    "

            # LOOP
            if self.hplayer.settings('loop') == 1:      cmdline += '^2O'
            elif self.hplayer.settings('loop') == 2:    cmdline += '^6X'
            else:                                       cmdline += '^3@'

            # VOLUME -/+
            cmdline += "     ^5P"+str(self.hplayer.settings('volume')).rjust(3)+" ^5O"

            # HEAD
            ind = min(self.hplayer.playlist.index()+1, self.hplayer.playlist.size())
            headline  = '^5M^1 ' + ( str(ind)+'/'+str(self.hplayer.playlist.size()) )
            headline += ' '+self.dirPlayback
            headline = headline[:18].ljust(18)
            # headline += '^0 ^5O'+str(self.hplayer.settings('volume')).rjust(3)

            self.line(0, headline)
            self.line(1, mutestate)
            self.line(2, playstate)
            self.line(3, ' ')
            self.line(4, cmdline)

        elif self.activePage == PAGE_MEDIA:
            self.line(0, '^8C^1 '+self.hplayer.files.currentDir())
            
            for k in range(4):
                l = '^6N' if k == self.microIndex else '  '
                m = os.path.splitext(self.microList[k])[0] if k < len(self.microList) else ''
                self.line(k+1, l+m)


    def scrollUp(self):
        if self.microIndex > 0:
            self.microIndex -= 1
        elif self.microOffset > 0:
            self.microOffset -= 1
        else:
            self.microIndex  = 3
            self.microOffset = len(self.hplayer.files.currentList())-4 
        self.microList = self.hplayer.files.currentList(True)[self.microOffset:][:4]
        

    def scrollDown(self):
        if self.microIndex < 3:
            self.microIndex += 1
        elif self.microOffset < len(self.hplayer.files.currentList())-4:
            self.microOffset += 1
        else:
            self.microIndex  = 0
            self.microOffset = 0
        self.microList = self.hplayer.files.currentList(True)[self.microOffset:][:4]


    def bind(self):
        
        @self.on('ready')
        @self.hplayer.files.on('filelist-updated')
        def updatelist(ev, *args):
            microL = self.hplayer.files.currentList(True)[self.microOffset:][:4]
            if self.microList != microL:
                self.microOffset = 0
                self.microIndex = 0
                self.microList = microL


        @self.hplayer.on('app-closing')
        def closing(ev, *args):
            self.off_all()
            self.page(PAGE_EXIT)
            self.refresh()

        #
        # BUTTON MUTE
        #  

        @self.on('MUTE-up')
        def mute_d(ev):
            if self.isFaded == 0:   
                self.emit('fade')
                self.isFaded = 1
            else:
                self.emit('unfade')
                self.isFaded = 0

        @self.on('MUTE-hold')
        def mute_h(ev):
            self._muteHolded = True
            if self.isFaded < 2:
                self.emit('fade', 1.0, 1.0, 1.0, 1.0)
                self.isFaded = 2

        @self.on('MUTE-holdup')
        def mute_hu(ev):
            self._muteHolded = False

        #
        # BUTTON FUNC
        #   

        @self.on('FUNC-down')
        def func_push(ev):
            self.clear()
            if self.activePage < PAGE_MAX:
                self.activePage += 1
            else:
                self.activePage = 0
            
            # When switching back to PAGE_MEDIA : go to current dir / file
            # if self.activePage == PAGE_MEDIA :
            #     if self.dirPlayback:
            #         self.hplayer.files.selectDir(self.dirPlayback)
            #         self.microOffset = max(0, self.hplayer.playlist.index()-3)
            #         self.microIndex = self.hplayer.playlist.index() - self.microOffset 
            #         self.microList = self.hplayer.files.currentList(True)[self.microOffset:][:4]
            #         # listchanged()


        @self.on('FUNC-hold')
        def func_hold(ev):
            self.activePage = PAGE_STATUS
            if self._muteHolded:
                self.page(PAGE_EXIT)
                self.refresh()
                Timer(.3, lambda: self.emit('hardreset')).start()

        #
        # BUTTON UP
        #      
            
        @self.on('UP-down')
        @self.on('UP-hold')
        def up(ev):
            if self.activePage == PAGE_MEDIA:
                self.scrollUp()

        
        @self.on('UP-up')
        def upu(ev):
            if self.activePage == PAGE_PLAYBACK:
                self.emit('prev')


        @self.on('UP-hold')
        def uph(ev):
            if self.activePage == PAGE_PLAYBACK:
                self.emit('skip', -1000)            

        #
        # BUTTON DOWN
        #      
        
        @self.on('DOWN-down')
        @self.on('DOWN-hold')
        def down(ev):
            if self.activePage == PAGE_MEDIA:
                self.scrollDown()

        
        @self.on('DOWN-up')
        def downu(ev):
            if self.activePage == PAGE_PLAYBACK:
                self.emit('next')


        @self.on('DOWN-hold')
        def downh(ev):
            if self.activePage == PAGE_PLAYBACK:
                self.emit('skip', 100)         
        #
        # BUTTON A
        #  

        @self.on('A-down')
        def a(ev):
            if self.activePage == PAGE_PLAYBACK:
                if self.hplayer.activePlayer().isPlaying():
                    self.emit('resume') if self.hplayer.activePlayer().isPaused() else self.emit('pause')
                else:
                    self.emit('play')

            elif self.activePage == PAGE_MEDIA:
                self.emit('play', self.hplayer.files.currentList(), self.microOffset+self.microIndex)
                self.dirPlayback = self.hplayer.files.currentDir()
                self.emit('unfade')
                self.isFaded = 0
                self.page(PAGE_PLAYBACK)


        @self.on('A-hold')
        def ah(ev):
            if self.activePage == PAGE_PLAYBACK:
                if self.hplayer.activePlayer().isPlaying():
                    self.emit('stop')
                    self.page(PAGE_MEDIA)

        #
        # BUTTON B
        #        

        @self.on('B-down')
        def b(ev):
            if self.activePage == PAGE_PLAYBACK:
                self.emit('loop', -1) if self.hplayer.settings('loop') > 0 else self.emit('loop', 1)


        @self.on('B-hold')
        def bh(ev):
            if self.activePage == PAGE_PLAYBACK:
                if self.hplayer.settings('loop') < 2: 
                    self.emit('loop', 2)


        #
        # BUTTON C
        #

        @self.on('C-down')
        @self.on('C-hold')
        def c(ev):
            if self.activePage == PAGE_PLAYBACK:
                self.emit('volume', self.hplayer.settings('volume')-1)

            elif self.activePage == PAGE_MEDIA:
                self.hplayer.files.prevDir()


        #
        # BUTTON D
        #

        @self.on('D-down')
        @self.on('D-hold')
        def d(ev):
            if self.activePage == PAGE_PLAYBACK:
                self.emit('volume', self.hplayer.settings('volume')+1)

            elif self.activePage == PAGE_MEDIA:
                self.hplayer.files.nextDir()


