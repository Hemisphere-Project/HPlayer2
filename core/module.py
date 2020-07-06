
from pymitter import EventEmitter
from termcolor import colored
import sys, threading

printlock = threading.Lock()

class EventEmitterX(EventEmitter):
    def emit(self, event, *args):
        # prepend event to args
        a = [event] + list(args)
        # self.log('HPLAYER', event, *a )
        super().emit(event, *a)
        # self.log('DONE.')


class Module(EventEmitterX):
    def __init__(self, hplayer, name, color):
        super().__init__(wildcard=True, delimiter=".")
        self.name = name.replace(" ", "_")
        self.nameP = colored(('['+self.name+']').ljust(10, ' ')+' ', color)
        self.hplayer = hplayer
        self.logEvents = True

    def log(self, *argv):
        with printlock:
            print(self.nameP, *argv)
            sys.stdout.flush()

    # Emit extended
    def emit(self, event, *args):
        
        fullEvent = self.name.lower() + '.' + event
        if self.logEvents:
            self.log('EVENT', fullEvent, *args )

        super().emit(event, *args) 
        self.hplayer.emit(fullEvent, *args)

        
