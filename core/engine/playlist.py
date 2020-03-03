from ..module import Module
import os
import re


class Playlist(Module):
    
    _playlist = []
    _index = 0
    
    def __init__(self, hplayer):
        super().__init__(hplayer, 'Playlist', 'yellow')

    def __call__(self):
        return self.export()

    def export(self):
        return self._playlist.copy()

    def onMediaEnd(self):
        # loop one
        if self.hplayer.settings.get('loop') == 1:
            self.playindex(self._index)

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


    # PLAY a playlist
    def play(self, plist=None, index=-1):
        if plist: 
            self.load(plist)
        
        if index >= 0:
            self.playindex(index)
        elif self._index >= 0:
            self.playindex(self._index)
        else:
            self.playindex(0)


    # PLAY at index
    def playindex(self, index):

        # Emit play event
        if 0 <= index < self.size() and os.path.isfile(self._playlist[index]):
            self._index = index
            self.emit('do-play', self._playlist[self._index], self._index)
        
        # Handle error
        else:
            self.emit('stop')
            self.emit('nomedia')

            if self.size() == 0:                    self.log("Play list empty")
            elif not (0 <= index < self.size()):    self.log("Index out of playlist range:", index, self._playlist)
            else:                                   self.log("Media not found:", self._playlist[index])


    # NEXT item in playlist
    def next(self):
        i = self._index + 1
        if i >= self.size():
            i = 0
        self.playindex(i)

    # PREVIOUS item in playlist
    def prev(self):
        i = self._index - 1
        if i < 0:
            i = self.size()-1
        self.playindex(i)

    # LAST item
    def last(self):
        self.playindex(self.size()-1)

    # first item
    def first(self):
        self.playindex(0)


    
