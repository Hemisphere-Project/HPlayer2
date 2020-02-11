from .base import BaseInterface

import time, os
import serial
from serial.tools import list_ports
from threading import Timer

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

        self.microIndex = 0
        self.microOffset = 0
        self.microList = []

        self._buffer = [None]*self.nLines        
        self._hardClear = True
        self._delegate = None

        self.init()
        

    # SERIAL receiver THREAD
    def listen(self):

        while self.isRunning():

            # find port
            if not self.port:
                for dev in list_ports.grep(self.filter):
                    self.port = dev.device
                    break
                if not self.port:
                    self.log("no device found.. retrying")
                    time.sleep(3)
            
            # connect to serial
            elif not self.serial:
                try:
                    self.serial = serial.Serial(self.port, 115200, timeout=.1)
                    self.log("connected to", self.port, "!")
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
                            say += (str(i+1)+" "+str(l['bold'])+"  "+l['txt']).ljust(26, ' ')
                            # self.log(data.encode())
                            l['dirty'] = False
                    
                    if say:
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
            self._buffer[i] = {'txt': '', 'bold': 0, 'dirty': True}

    # change line n
    def line(self, n, txt, bold=False):
        if txt != self._buffer[n]['txt'] or int(bold) != self._buffer[n]['bold']:
            self._buffer[n]['txt'] = txt
            self._buffer[n]['bold'] = int(bold)
            self._buffer[n]['dirty'] = True


    # change active page
    def page(self, p):
        self.activePage = p


    def init(self):
        
        self.bind()
        self.clear()
        self.timer(0.05, lambda: self.page(PAGE_MEDIA))
        self.refresh()



    def refresh(self):

        if self.activePage == PAGE_WELCOME:

            self.line(1, '       KXKM', False)
            self.line(2, '    RPi-Teleco', True)
            self.line(3, '       0.1', False)

        elif self.activePage == PAGE_STATUS:

            self.line(0, 'STATUS', True)
            self.line(1, '', False)
            self.line(2, 'Volume: '+' '+str(self.hplayer.settings('volume')), False)
            self.line(3, ' Peers: '+' '+str(self.hplayer.interface('zyre').activeCount()), False)
            self.line(4, '  Link: '+' ?', False)
        
        elif self.activePage == PAGE_PLAYBACK:

            player = self.hplayer.activePlayer()
            status = player.status()

            playstate = 'STOP  '
            loopstate = ''.ljust(4)
            timestate = ''
            if player.isPlaying():
                playstate = 'PAUSE ' if player.isPaused() else 'PLAY  '
                if status['media']:
                    playstate += status['media'].split('/')[-1]
                timestate = (str( round(status['time'], 1) )+'" ')

            if self.hplayer.settings('loop') == 1:
                loopstate += 'LOOP   '
            elif self.hplayer.settings('loop') == 2:
                loopstate += 'LOOPALL'
            else: loopstate += '->'

            self.line(0, 'PLAYBACK'.ljust(17)+str(self.hplayer.settings('volume')).rjust(3), True)
            self.line(1, timestate.rjust(21), False)
            self.line(2, playstate, False)
            self.line(3, '', False)
            self.line(4, loopstate, False)

        elif self.activePage == PAGE_MEDIA:
            self.line(0, 'MEDIA /'+self.hplayer.files.currentDir(), True)
            
            for k in range(4):
                l = '> ' if k == self.microIndex else '  '
                m = os.path.splitext(self.microList[k])[0] if k < len(self.microList) else ''
                self.line(k+1, l+m, False)

            


    def bind(self):
        
        @self.hplayer.files.on('filelist-updated')
        def listchanged(*args):
            self.microOffset = 0
            self.microIndex = 0
            self.microList = self.hplayer.files.activeList(True)[self.microOffset:][:4]

        @self.on('FUNC-down')
        def func_push():
            self.clear()
            if self.activePage < PAGE_MAX:
                self.activePage += 1
            else:
                self.activePage = 0
            
            # When switching back to PAGE_MEDIA
            if self.activePage == PAGE_MEDIA :
                # self.microOffset = max(0, self.hplayer.playlist.index()-3)
                # self.microIndex = self.hplayer.playlist.index() - self.microOffset 
                # self.microList = self.hplayer.files.activeList(True)[self.microOffset:][:4]
                listchanged()


        @self.on('FUNC-hold')
        def func_hold():
            self.activePage = PAGE_STATUS
            
            
        @self.on('UP-down')
        @self.on('UP-hold')
        def up():
            if self.activePage in [PAGE_STATUS, PAGE_PLAYBACK]:
                self.emit('volume', self.hplayer.settings('volume')+1)

            elif self.activePage == PAGE_MEDIA:
                    
                if self.microIndex > 0:
                    self.microIndex -= 1
                elif self.microOffset > 0:
                    self.microOffset -= 1
                else:
                    self.microIndex  = 3
                    self.microOffset = len(self.hplayer.files.activeList())-4 
                self.microList = self.hplayer.files.activeList(True)[self.microOffset:][:4]
                    

        
        @self.on('DOWN-down')
        @self.on('DOWN-hold')
        def down():
            if self.activePage in [PAGE_STATUS, PAGE_PLAYBACK]:
                self.emit('volume', self.hplayer.settings('volume')-1)

            elif self.activePage == PAGE_MEDIA:

                if self.microIndex < 3:
                    self.microIndex += 1
                elif self.microOffset < len(self.hplayer.files.activeList())-4:
                    self.microOffset += 1
                else:
                    self.microIndex  = 0
                    self.microOffset = 0
                self.microList = self.hplayer.files.activeList(True)[self.microOffset:][:4]

        #
        # BUTTON A
        #  

        @self.on('A-down')
        def a():
            if self.activePage == PAGE_STATUS:
                pass

            elif self.activePage == PAGE_PLAYBACK:
                if self.hplayer.activePlayer().isPlaying():
                    self.emit('resume') if self.hplayer.activePlayer().isPaused() else self.emit('pause')
                else:
                    self.emit('play')

            elif self.activePage == PAGE_MEDIA:
                micro = self.hplayer.files.activeList()[self.microOffset:]
                if self.microIndex < len(micro):  
                    self.emit('play', micro[self.microIndex])
                    self.page(PAGE_PLAYBACK)

        @self.on('A-hold')
        def ah():
            if self.activePage == PAGE_STATUS:
                pass

            elif self.activePage == PAGE_PLAYBACK:
                if self.hplayer.activePlayer().isPlaying():
                    self.emit('stop')

            elif self.activePage == PAGE_MEDIA:
                pass

        #
        # BUTTON B
        #        

        @self.on('B-down')
        def b():
            if self.activePage == PAGE_STATUS:
                pass

            elif self.activePage == PAGE_PLAYBACK:
                self.emit('unloop') if self.hplayer.settings('loop') > 0 else self.emit('loop', 1)

            elif self.activePage == PAGE_MEDIA:
                self.emit('play', self.hplayer.files.activeList(), self.microOffset+self.microIndex)
                self.page(PAGE_PLAYBACK)

        @self.on('B-hold')
        def bh():
            if self.activePage == PAGE_STATUS:
                pass

            elif self.activePage == PAGE_PLAYBACK:
                if self.hplayer.settings('loop') < 2: 
                    self.emit('loop', 2)

            elif self.activePage == PAGE_MEDIA:
                pass

        #
        # BUTTON C
        #

        @self.on('C-down')
        def c():
            if self.activePage == PAGE_STATUS:
                pass

            elif self.activePage == PAGE_PLAYBACK:
                self.emit('prev')
                pass    # TODO: SKIP ON HOLD

            elif self.activePage == PAGE_MEDIA:
                self.hplayer.files.prevDir()

        @self.on('C-hold')
        def ch():
            if self.activePage == PAGE_STATUS:
                pass

            elif self.activePage == PAGE_PLAYBACK:
                pass    # TODO: SKIP ON HOLD

            elif self.activePage == PAGE_MEDIA:
                self.hplayer.files.prevDir()

        #
        # BUTTON D
        #

        @self.on('D-down')
        def d():
            if self.activePage == PAGE_STATUS:
                pass

            elif self.activePage == PAGE_PLAYBACK:
                self.emit('next')

            elif self.activePage == PAGE_MEDIA:
                self.hplayer.files.nextDir()

        @self.on('D-hold')
        def dh():
            if self.activePage == PAGE_STATUS:
                pass

            elif self.activePage == PAGE_PLAYBACK:
                pass    # TODO: SKIP ON HOLD

            elif self.activePage == PAGE_MEDIA:
                self.hplayer.files.nextDir()