from ..module import Module
import os
import re


class Playlist(Module):
    
    _playlist = []
    _index = 0
    
    def __init__(self, hplayer):
        super().__init__(hplayer, 'Playlist', 'yellow')


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


    # CHECK EXT
    def validExt(self, filename):
        for p in self.hplayer.players():
            if p.validExt(filename):
                return True
        return False

    # SET Playlist
    def update(self):
        self.emit('updated', self._playlist)        # TODO => save playlist !  // # TODO => if playlist > 0 and not isPlaying: trig autoplay !

    # Playlist length
    def size(self):
        return len(self._playlist)

    # CLEAR Playlist
    def clear(self):
        self._playlist = []
        self.emit('cleared')
        self.emit('stop')

    # ADD to Playlist
    def add(self, media):
        if not type(media) is list: media = [media]
        media = [m for m in media if os.path.isfile(m) and self.validExt(m)]
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
        self._playlist = self.buildList(playlist)
        self._index = -1
        self.update()


    # PLAY a playlist
    def play(self, plist):
        self.load(plist)
        self.playindex(0)


    # PLAY at index
    def playindex(self, index):

        # Emit play event
        if 0 <= index < self.size() and os.path.isfile(self._playlist[index]):
            self._index = index
            self.emit('doplay', self._playlist[self._index], self._index)
        
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


    # BUILD LIST RECURSIVE
    def buildList(self, entries):
        liste = []
        if not isinstance(entries, (list,)):
            entries = [entries]

        for entry in entries:

            # ABSOLUTE PATH

            # full path directory -> add content recursively
            if os.path.isdir(entry):
                dirContent = [os.path.join(entry, f) for f in os.listdir(entry) if not f.startswith('.')]
                dirContent.sort()
                liste.extend(self.buildList( dirContent ))

            # full path file -> add it
            elif os.path.isfile(entry):
                if self.validExt(entry):
                    liste.append(entry)

            # full path file with WILDCARD
            ## TODO PROBABLY BROKEN !
            # elif entry[0] == '/' and len(glob.glob(entry)) > 0:
            # 	for e in glob.glob(entry):
            #         if os.path.isfile(e):
            #             liste.extend(e)

            # RELATIVE PATH

            # check each base path
            else:
                for base in self.hplayer.files.root_paths:
                    if os.path.isdir(base):
                        fullpath = os.path.join(base, entry)
                        # relative path directory -> add content recursively
                        if os.path.isdir(fullpath):
                            liste.extend(self.buildList(fullpath))
                            break
                        # relative path file -> add content recursively
                        elif os.path.isfile(fullpath):
                            if self.validExt(entry):
                                liste.append(fullpath)
                                break

                        # relative path file with WILDCARD
                        else:
                            globlist = []
                            for root, dirs, files in os.walk(base, topdown=False):
                               for name in files:
                                  fpath = os.path.join(root, name)
                                  match = re.match( r''+fullpath.replace('*','.*'), fpath, re.M|re.I)
                                  if ('/.' not in fpath) and match:
                                    	globlist.append(fpath)
                            #print(globlist)
                            for e in globlist:
                                if os.path.isfile(e) and self.validExt(e):
                                    liste.append(e)
                            break

        liste.sort()
        return liste
