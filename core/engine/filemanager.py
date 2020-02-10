from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler
from threading import Timer
import os
import pathlib
from ..module import Module

class FileManager(Module):
    def __init__(self, hplayer, roots=None):
        super().__init__(hplayer, 'Files', 'yellow')

        self.root_paths = []
        self.unified_dir = []
        self.active_dir = 0
        self.refreshTimer = None
        self.pathObservers = []
        
        @self.on('file-changed')
        def deferredUpdate(*args): 
            if not self.refreshTimer:
                self.refreshTimer = Timer(3.0, self.refresh)
                self.refreshTimer.start()

        if roots: self.add(roots)

    def add(self, path):
        """
        Set root directories with attached watchdogs 
        """
        if not isinstance(path, list): path = [path]
        for p in path:
            if not os.path.isdir(p):
                p = '/tmp'+os.path.abspath(p)
                pathlib.Path(p).mkdir(parents=True, exist_ok=True)
                self.log("Basepath not found, using "+p+" instead")
            self.root_paths.append(p)
            handler = PatternMatchingEventHandler("*", "", False, True)
            handler.on_any_event = lambda e: self.emit('file-changed', e)
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
            listDirs = [d for d in next(os.walk(path))[1] if not d.startswith('.')]
        listDirs = sorted(list(dict.fromkeys(listDirs)))
        # listDirs.insert(0,'')
        self.unified_dir = listDirs
        self.log('directory list updated', self.unified_dir)
        self.emit('dirlist-updated')


    def selectDir(self, i):
        """
        Set working directory by index or value.
        Active directory must exist in available_dir list.
        """
        if isinstance(i, int):
            if i < 0: i = len(self.unified_dir)+i
            if i >= 0 and i < len(self.unified_dir): self.active_dir = i
        elif i in self.unified_dir: 
            self.active_dir = self.unified_dir.index(i)
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
        return self.currentDir()


    def prevDir(self):
        """
        Go to previous working directory. 
        """
        self.active_dir -= 1
        if self.active_dir < 0: 
            self.active_dir = len(self.unified_dir)-1
        return self.currentDir()


    def currentIndex(self):
        """
        Get working directory index
        """
        return self.active_dir


    def maxIndex(self):
        """
        Get number of directories
        """
        return len(self.unified_dir)


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


