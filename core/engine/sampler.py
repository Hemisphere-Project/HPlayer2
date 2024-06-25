from ..module import Module
import core.players as playerlib
from collections import OrderedDict
import os

class Sampler(Module):

    def __init__(self, hplayer, ptype, poly):
        super().__init__(hplayer, 'Sampler', 'magenta')
        
        self._players = OrderedDict()        
        self._usedHistory = []

        # Players
        PlayerClass = playerlib.getPlayer(ptype)
        for i in range(poly):
            name = 'player'+str(i)
            p = PlayerClass(self, name)
            self._players[name] = p
            self.logQuietEvents.append(name+'.status')

            # Players stopped (remove from in-use list)
            @p.on('stopped')
            def pend(ev, *args):
                self._usedHistory = [x for x in self._usedHistory if self._players[x].isPlaying()]
                if all( [not p.isPlaying() for p in self.players()] ):
                    self.emit('stopped')

            # Players ready
            @p.on('ready')
            def pready(ev, *args):
                if all( [p.status('isReady') for p in self.players()] ):
                    self.emit('ready')

            


    def player(self, name):
        if name not in self._players:
            self.log("player", name, "not found")
        return self._players[name]


    def players(self):
        return list(self._players.values())


    # CHECK EXT
    def validExt(self, filename):
        return self.players()[0].validExt(filename) # ask player0

    #
    # Sampler STATUS
    #

    # SET/GET is running
    def isRunning(self, state=None):
        return all( [p.isRunning(state) for p in self.players()] )

    # STATUS Set
    def status(self):
        return [p.status() for p in self.players()]

    def isPlaying(self, media=None):
        if not media: 
            return any( [p.isPlaying() for p in self.players()] )
        _media = self.parent.files.listFiles(media)[0]
        return any( [p.isPlaying() and p.status('media') == _media for p in self.players()] )

    def isPaused(self, media=None):
        if not media:
            return any( [p.isPaused() for p in self.players()] )
        _media = self.parent.files.listFiles(media)[0]
        return any( [p.isPaused() and p.status('media') == _media for p in self.players()] )

    def isReady(self):
        return all( [p.isReady() for p in self.players()] )

    #
    # Sampler CONTROLS
    #

    # START
    def start(self):
        for p in self.players():
            p.start()

    # QUIT
    def quit(self):
        for p in self.players():
            p.quit()
    
    # Play Media
    def play(self, media, oneloop=False):
        freeP = None
        _media = self.parent.files.listFiles(media)[0]  # find first matching media
        if not _media:
            self.log('media not found: ', media)

        for p in self.players():   # media already played somewhere
            if p.status('media') == _media:
                freeP = p.name
                break

        if not freeP and len(self._usedHistory) < len(self.players()):
            for p in self.players():   # find available player
                if not p.isPlaying():
                    freeP = p.name
                    break

        if not freeP and len(self._usedHistory) > 0:
            freeP = self._usedHistory.pop(0)   # no player available, take the older one

        if not freeP:
            freeP = self.players()[0].name   # default: take 0

        self._players[freeP].play(_media)
        self._players[freeP]._applyOneLoop(oneloop)

        self._usedHistory = [x for x in self._usedHistory if x != freeP]
        self._usedHistory.append(freeP)

    # STOP Playback
    def stop(self, media=None):
        _media = self.parent.files.listFiles(media)[0]  # find first matching media
        for p in self.players(): 
            if not _media or p.status('media') == _media:
                p.stop()

    # PAUSE Playback
    def pause(self, media=None):
        _media = self.parent.files.listFiles(media)[0]  # find first matching media
        for p in self.players(): 
            if not _media or p.status('media') == _media:
                p.pause()

    # RESUME Playback
    def resume(self, media=None):
        _media = self.parent.files.listFiles(media)[0]  # find first matching media
        for p in self.players(): 
            if not _media or p.status('media') == _media:
                p.resume()

    

    
    
