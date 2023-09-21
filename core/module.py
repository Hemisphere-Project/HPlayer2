
from pymitter import EventEmitter
from termcolor import colored
import sys, threading


def safe_print(*args, sep=" ", end="", **kwargs):
    joined_string = sep.join([ str(arg) for arg in args ])
    print(joined_string  + "\n", sep=sep, end=end, **kwargs)

delimTimer = None
def delimiter():
    global delimTimer
    if delimTimer:
        delimTimer.cancel()
    delimTimer = threading.Timer(.5, lambda: safe_print(colored('-'*80, 'grey')))
    delimTimer.start()


class EventEmitterX(EventEmitter):
    def emit(self, event, *args):
        # prepend event to args
        a = [event] + list(args)
        super().emit(event, *a)


class Module(EventEmitterX):
    def __init__(self, parent, name, color):
        super().__init__(wildcard=True, delimiter=".")
        self.name = name.replace(" ", "_")
        self.nameP = colored(('['+self.name+']').ljust(10, ' ')+' ', color)
        self.parent = parent
        self.logQuietEvents = []    # list of not-logged events  '*' for full quiet

    def log(self, *argv):
        safe_print(self.nameP, *argv)
        sys.stdout.flush()
        delimiter()

    # Emit extended
    def emit(self, event, *args):
        fullEvent = self.name.lower() + '.' + event
        if self.parent or not '.' in event: # child module or top-level event
            if not '*' in self.logQuietEvents and not event in self.logQuietEvents:
                self.log('-', event, *args )

        super().emit(event, *args) 
        if self.parent: self.parent.emit(fullEvent, *args)

        
