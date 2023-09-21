from ..module import Module
import os
import re
from random import randrange, shuffle


class Playlist(Module):
    
    _playlist = []
    _index = 0
    _lastran = -1
    
    def __init__(self, hplayer, name='Playlist'):
        super().__init__(hplayer, name, 'yellow')
        self.hplayer = hplayer
        
        # Custom action to do on playlist end
        self.onEnd = None
        @self.on('end')
        def _onEnd(ev, *args):
            if self.onEnd: self.onEnd()
            
        # Autobind to player
        hplayer.autoBind(self)
            

    def __call__(self):
        return self.export()

    def export(self):
        return self._playlist.copy()

    def onMediaEnd(self):
        # loop one
        if self.hplayer.settings.get('loop') == 1:
            self.playindex(self._index)

        # only one
        elif self.hplayer.settings.get('loop') == -1:
            self.emit('end')

        # playlist is not finished OR can loop
        elif self._index < self.size()-1 or self.hplayer.settings.get('loop') == 2:
            self.next()

        # done
        else:
            self.emit('end')

    # SET Playlist
    def update(self):
        self.emit('updated', self._playlist)        # TODO => save playlist !  // # TODO => if playlist > 0 and not isPlaying: trig autoplay !

    # Playlist length
    def size(self):
        return len(self._playlist)

    # Playlist index
    def index(self):
        return self._index

    # Playlist current item
    def track(self):
        return self.trackAtIndex(self._index)

    # CLEAR Playlist
    def clear(self):
        self._playlist = []
        self.emit('cleared')
        self.update()
        self.emit('stop')   # trigger player stop

    # ADD to Playlist
    def add(self, media):
        if not type(media) is list: media = [media]
        media = [m for m in media if os.path.isfile(m) and self.hplayer.files.validExt(m)]
        if len(media) > 0:
            self._playlist.extend(media)
            self.emit('added', media)
            self.update()

    # REMOVE from Playlist
    def remove(self, index):
        index = int(index)
        if len(self._playlist) > index:
            del self._playlist[index]
            self.emit('removed', index) 
            self.update()
            if index < self._index: self._index -= 1
            elif index == self._index: self.next()
            

    # LOAD A PLAYLIST
    def load(self, playlist=None):
        self._playlist = self.hplayer.files.listFiles(playlist)
        self._index = -1
        self.update()

    # JUST SET INDEX TO -1
    def rearm(self):
        self._index = -1
        
    # RANDOMIZE CURRENT PLAYLIST
    def randomize(self):
        shuffle(self._playlist)
        self.rearm()

    # PLAY a playlist
    def play(self, plist=None, index=-1, pause=False):
        self.onEnd = None
        
        if plist: 
            self.load(plist)
        
        if index >= 0:
            self.playindex(index, pause)
        elif self._index >= 0:
            self.playindex(self._index, pause)
        else:
            self.playindex(0, pause)

    # PLAY a playlist and execute event on end
    def playthen(self, plist=None, then=None, pause=False):
        self.play(plist, pause=pause)
        if then:
            self.onEnd = lambda: self.emit(then['event'], *then['data'])

    # PLAY at index
    def playindex(self, index, pause=False):

        # Emit play event
        if 0 <= index < self.size() and os.path.isfile(self._playlist[index]):
            self._index = index
            self.emit('do-play', self._playlist[self._index], self._index, pause)
        
        # Handle error
        else:
            self.emit('stop')
            self.emit('nomedia')

            if self.size() == 0:                    self.log("Play list empty")
            elif not (0 <= index < self.size()):    self.log("Index out of playlist range:", index, self._playlist)
            else:                                   self.log("Media not found:", self._playlist[index])


    # NEXT item in playlist
    def next(self):
        self.playindex( self.nextIndex() )

    # PREVIOUS item in playlist
    def prev(self):
        self.playindex( self.prevIndex() )

    # LAST item
    def last(self):
        self.playindex(self.size()-1)

    # first item
    def first(self):
        self.playindex(0)
        
    # random item
    def random(self):
        if self.size() > 0:
            ran = randrange(self.size())
            if self.size() > 1:
                while ran == self._lastran:
                    ran = randrange(self.size())
            self._lastran = ran
            self.playindex( ran )
        print('RAN', self.size())

    
    ## NEXT index
    def nextIndex(self):
        return (self._index + 1) % self.size() if self.size() > 0 else 0

    # Playlist NEXT item
    def nextTrack(self):
        return self.trackAtIndex( self.nextIndex() )

    # PREVIOUS index in playlist
    def prevIndex(self):
        i = self._index - 1
        if i < 0: i = self.size()-1
        return i if i > 0 else 0

    # Playlist PREVIOUS item
    def prevTrack(self):
        return self.trackAtIndex( self.prevIndex() )

    # LAST item
    def lastIndex(self):
        i = self._index + 1
        return i if i < self.size() else 0

    # Playlist LAST item
    def lastTrack(self):
        return self.trackAtIndex(self.size()-1)

    # first item
    def firstIndex(self):
        return 0

    # Playlist first item
    def firstTrack(self):
        return self.trackAtIndex(0)

    # find item
    def findIndex(self, pattern):
        pattern = pattern.replace('*', '.+')
        pattern = pattern.replace('?', '.')
        for k,media in enumerate(self._playlist):
            if re.search(pattern, media):
                return k
        return -1

    # Playlist item at index
    def trackAtIndex(self, index):
        if index < 0 or index >= len(self._playlist):
            return None
        return self._playlist[index]
