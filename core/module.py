
from pymitter import EventEmitter
from termcolor import colored

class Module(EventEmitter):
    def __init__(self, hplayer, name, color):
        super().__init__(wildcard=True, delimiter=".")
        self.name = name.replace(" ", "_")
        self.nameP = colored(('['+self.name+']').ljust(10, ' ')+' ', color)
        self.hplayer = hplayer
        self.logEvents = True

    def log(self, *argv):
        print(self.nameP, *argv)

    # Emit extended
    def emit(self, event, *args):
        if self.logEvents:
            self.log('EVENT',  self.name.lower() + '.' + event, *args )
        self.hplayer.emit( self.name.lower() + '.' + event, *args )
        super().emit(event, *args)