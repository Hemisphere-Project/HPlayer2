from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler
from threading import Timer
from collections import OrderedDict
import os
import re
import pathlib
from ..module import Module

class FileManager(Module):
    def __init__(self, hplayer, roots=None):
        super().__init__(hplayer, 'Files', 'yellow')

        self.root_paths = []
        self.unified_dir = []
        self.active_dir = 0
        self.active_list = []
        self.refreshTimer = None
        self.pathObservers = []
        
        @self.on('file-changed')                # file changed on disk -> trigger full refresh
        @self.hplayer.on('player-added')        # new player means new authorized extension -> trigger list refresh
        def deferredUpdate(ev, *args):
            if self.refreshTimer:
                self.refreshTimer.cancel()
            self.refreshTimer = Timer(.5, self.refresh)
            self.refreshTimer.start()

        if roots: 
            self.add(roots)
            

    def __call__(self, directory=None, fullpath=False):
        """
        Export entire file tree
        """
        if not directory:
            directory = self.listDir()
        elif not isinstance(directory, list): 
            directory = [directory]

        tree = OrderedDict()
        for d in directory:
            fl = self.listFiles(d)
            if not fullpath:
                fl = [f.split(d+'/')[-1] for f in fl] 
            tree[d] = fl

        return tree


    def add(self, path):
        """
        Set root directories with attached watchdogs 
        """

        # filter .tmp changes
        def onChange(e):
            if not e.src_path.endswith('.tmp'):
                self.emit('file-changed', e)

        if not isinstance(path, list): 
            path = [path]

        for p in path:
            if not os.path.isdir(p):
                self.log("Basepath "+p+" not found... ignoring")
                continue
                # p = '/tmp'+os.path.abspath(p)
                # pathlib.Path(p).mkdir(parents=True, exist_ok=True)
            else:
                self.log("Adding "+p+" as root paths")
            self.root_paths.append(p)
            handler = PatternMatchingEventHandler("*", None, False, True)
            handler.on_any_event = onChange
            my_observer = Observer()
            my_observer.schedule(handler, p, recursive=True)
            my_observer.start()
            self.pathObservers.append(my_observer)
        self.refresh()


    def refresh(self):
        """
        Update directory list
        """
        if self.refreshTimer:
            self.refreshTimer.cancel()
            self.refreshTimer = None
        listDirs = []
        for path in self.root_paths:
            listDirs.extend([d for d in next(os.walk(path))[1] if not d.startswith('.')])
        listDirs = sorted(list(dict.fromkeys(listDirs)))
        # listDirs.insert(0,'')
        self.unified_dir = listDirs
        # self.log('directory list updated', self.unified_dir)
        self.selectDir( self.active_dir )   
        self.emit('dirlist-updated', self.unified_dir)

    
    def listDir(self):
        """
        List available directories
        """
        return self.unified_dir.copy()


    def selectDir(self, i):
        """
        Set working directory by index or value.
        Active directory must exist in unified_dir list.
        Refresh cached files active_list
        """
        if isinstance(i, int):
            if i < 0: i = len(self.unified_dir)+i
            if i < 0: i = 0
            if len(self.unified_dir) > 0:
                self.active_dir = i % len(self.unified_dir)
            else:
                self.active_dir = 0
        elif i in self.unified_dir: 
            self.active_dir = self.unified_dir.index(i)
        
        self.active_list = self.listFiles( self.currentDir() )
        
        self.emit('filelist-updated', self.active_list)

        return self.currentDir()


    def currentDir(self):
        """
        Get working directory. 
        This is a relative directory: could be in any of the bath_paths
        """
        return self.unified_dir[self.active_dir] if self.active_dir < len(self.unified_dir) else ''


    def nextDir(self):
        """
        Go to next working directory. 
        """
        self.active_dir += 1
        if self.active_dir >= len(self.unified_dir): 
            self.active_dir = 0
        return self.selectDir(self.active_dir)


    def prevDir(self):
        """
        Go to previous working directory. 
        """
        self.active_dir -= 1
        if self.active_dir < 0: 
            self.active_dir = len(self.unified_dir)-1
        return self.selectDir(self.active_dir)


    def currentIndex(self):
        """
        Get working directory index
        """
        return self.active_dir


    def lastIndex(self):
        """
        Get number of directories
        """
        return len(self.unified_dir)-1


    def nextIndex(self):
        """
        Get next directory index
        """
        i = self.active_dir + 1
        if i >= len(self.unified_dir): 
            i = 0
        return i


    def prevIndex(self):
        """
        Get prev directory index
        """
        i = self.active_dir - 1
        if i < 0: 
            i = len(self.unified_dir)-1
        return i


    def currentList(self, relative=False):
        """
        List of files in activeDir (cached)
        """
        liste = self.active_list.copy()
        if relative:
            c = self.currentDir()
            relativeliste = []
            for path in self.root_paths:
                p = os.path.join(path,c)+'/'
                relativeliste.extend([ l[len(p):] for l in liste if l.startswith(p)])
            return relativeliste
        return liste 


    def validExt(self, filename):
        """
        Check with all players to validate extension
        """
        for p in self.hplayer.players():
            if p.validExt(filename):
                return True
        return False


    def listFiles(self, entries):
        """
        Create recursive list of files based on source (can be files, folders, ...)
        """
        
        liste = []
        if not isinstance(entries, (list,)):
            entries = [entries]

        for entry in entries:

            # ABSOLUTE PATH

            # full path directory -> add content recursively
            if os.path.isdir(entry):
                dirContent = [os.path.join(entry, f) for f in os.listdir(entry) if not f.startswith('.')]
                dirContent.sort()
                liste.extend(self.listFiles( dirContent ))

            # full path file -> add it
            elif os.path.isfile(entry):
                if self.validExt(entry):
                    liste.append(entry)
                # else:
                #     self.log('invalid ext', entry)

            # full path file with WILDCARD
            ## TODO PROBABLY BROKEN !
            # elif entry[0] == '/' and len(glob.glob(entry)) > 0:
            # 	for e in glob.glob(entry):
            #         if os.path.isfile(e):
            #             liste.extend(e)

            # RELATIVE PATH

            # check each base path
            else:
                for base in self.root_paths:
                    if os.path.isdir(base):
                        fullpath = os.path.join(base, entry)
                        # relative path directory -> add content recursively
                        if os.path.isdir(fullpath):
                            liste.extend(self.listFiles(fullpath))
                            break
                        # relative path file -> add content recursively
                        elif os.path.isfile(fullpath):
                            if self.validExt(entry):
                                liste.append(fullpath)
                            # else:
                            #     self.log('invalid ext', fullpath)
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

        liste.sort()
        return liste

