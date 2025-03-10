from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler
from threading import Timer
from collections import OrderedDict
import os
import re
import pathlib
from ..module import Module

class FileManager(Module):
    def __init__(self, hplayer):
        super().__init__(hplayer, 'Files', 'yellow')
        self.hplayer = hplayer

        self.root_paths = []
        self.unified_dir = []
        self.active_dir = 0
        self.active_list = []
        self.refreshTimer = None
        self.pathObservers = []
        
        # self.logQuietEvents.append('file-changed')
        
        # Defered update (file change might trigger multiple events)
        @self.on('file-changed')                # file changed on disk -> trigger full refresh
        def deferredUpdate(ev, *args):
            if args[0].event_type == 'modified':
                print(args[0].event_type)
                if self.refreshTimer:
                    self.refreshTimer.cancel()
                self.refreshTimer = Timer(.5, self.refresh)
                self.refreshTimer.start()

        # Instant update: new player means new authorized extension -> trigger list refresh
        @self.parent.on('player-added')        # new player means new authorized extension -> trigger list refresh
        @self.parent.on('sampler-added')        # new player means new authorized extension -> trigger list refresh
        def instantUpdate(ev, *args):
            if self.refreshTimer:
                self.refreshTimer.cancel()
            self.refresh()
            
        # Autobind to player
        hplayer.autoBind(self)
            

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
            if e.src_path.endswith('.tmp'): return
            if e.src_path.endswith('project.json'): return
            if e.event_type != 'modified': return
            self.emit('file-changed', e)

        if not isinstance(path, list): 
            path = [path]

        doRefresh = False
        for p in path:
            if not os.path.isdir(p):
                self.log("Basepath "+p+" not found... ignoring")
                continue
                # p = '/tmp'+os.path.abspath(p)
                # pathlib.Path(p).mkdir(parents=True, exist_ok=True)
            else:
                self.log("Adding "+p+" as root paths")
            self.root_paths.append(p)
            handler = PatternMatchingEventHandler(
                            patterns=["*"],
                            ignore_patterns=None,
                            ignore_directories=False,
                            case_sensitive=True
                        )
            handler.on_any_event = onChange
            my_observer = Observer()
            my_observer.schedule(handler, p, recursive=True)
            my_observer.start()
            self.pathObservers.append(my_observer)
            doRefresh = True
        

    def refresh(self):
        """
        Update directory list
        """
        if self.refreshTimer:
            self.refreshTimer.cancel()
            self.refreshTimer = None
        addRoot = False
        listDirs = []
        for path in self.root_paths:
            if len(self.listFiles(path, '')) > 0: addRoot = True
            listDirs.extend([d for d in next(os.walk(path))[1] if not d.startswith('.') and d != "System Volume Information" ])
        listDirs = sorted(list(dict.fromkeys(listDirs)))
        listDirs = [d for i,d in enumerate(listDirs) if d not in listDirs[:i]]
        if addRoot: listDirs.insert(0,'/')
        self.unified_dir = listDirs
        self.emit('dirlist-updated', self.unified_dir)
        self.selectDir( self.active_dir )   

    
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
        
        self.emit('activedir-updated', self.currentDir(), self.currentIndex())
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


    def currentList(self, relative=False, filtered=False):
        """
        List of files in activeDir (cached)
        """
        liste = self.active_list.copy()
        c = self.currentDir()
        relativeliste = []
        for path in self.root_paths:
            p = os.path.join(path,c)+'/'
            p = p.replace('//','/')
            relativeliste.extend([ l[len(p):] for l in liste if l.startswith(p)])
        if relative:    
            liste = relativeliste
        if filtered:
            return [f for f in liste if self.hplayer.settings('filter').lower() in f.lower()]
        return liste 


    def validExt(self, filename):
        """
        Check with all players to validate extension
        """
        for p in self.hplayer.players():
            if p.validExt(filename):
                return True
        for s in self.hplayer.samplers():
            if s.validExt(filename):
                return True
        return False


    def listFiles(self, entries, origin=None):
        """
        Create recursive list of files based on source (can be files, folders, ...)
        """
        liste = []
        if not isinstance(entries, (list,)):
            entries = [entries]

        for entry in entries:
            if not entry: continue

            # PREVENT ROOT
            if entry == '/': entry = ''

            # ABSOLUTE PATH

            # full path directory -> add content recursively
            if entry.startswith('/') and os.path.isdir(entry):
                dirContent = [os.path.join(entry, f) for f in os.listdir(entry) if not f.startswith('.')]
                dirContent.sort()
                if origin == '':  dirContent = [f for f in dirContent if os.path.isfile(f)] # prevent subfolders digging if scanning 'root' directory
                liste.extend(self.listFiles( dirContent ))

            # full path file -> add it
            elif entry.startswith('/') and os.path.isfile(entry):
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
                        # relative path directory -> add content recursively (if not root path !)
                        if os.path.isdir(fullpath):
                            liste.extend(self.listFiles(fullpath, entry))
                            continue
                        # relative path file -> add content
                        elif os.path.isfile(fullpath):
                            if self.validExt(entry):
                                liste.append(fullpath)
                            # else:
                            #     self.log('invalid ext', fullpath)
                            continue

                        # relative path file with WILDCARD
                        else:
                            globlist = []
                            for root, dirs, files in os.walk(base, topdown=False):
                               for name in files:
                                  fpath = os.path.join(root, name)
                                  match = re.fullmatch( r''+fullpath.replace('*','.*'), fpath, re.M|re.I)
                                #   print(fpath, fullpath.replace('*','.*'), match)
                                  if ('/.' not in fpath) and match:
                                    	globlist.append(fpath)
                            # print(globlist)
                            for e in globlist:
                                if os.path.isfile(e) and self.validExt(e):
                                    liste.append(e)

        liste.sort()
        # print(liste)
        return liste

