
from pymitter import EventEmitter
from termcolor import colored
import sys, threading


def safe_print(*args, sep=" ", end="", **kwargs):
    joined_string = sep.join([ str(arg) for arg in args ])
    print(joined_string  + "\n", sep=sep, end=end, **kwargs)

# The delimiter line is printed 0.5 s after the LAST log line. This used to be a threading.Timer
# per log line (cancel the previous, start a new one): one OS thread created and torn down for
# every line, hundreds per second during a chase or a peer-link storm. On the Biennale slaves
# (Pi 3B+, Python 3.14) that churn ended in `RuntimeError: can't start new thread` raised from
# whatever else needed a thread at that moment — the zyre link timers, on kouagou02/03,
# 2026-09-18..21 — and a peer link stalled for good. One long-lived daemon thread now waits on
# an event and sleeps out the quiet period; log() only stamps the time and sets the event.
import time
_delimLast = [0.0]
_delimEvent = threading.Event()
_delimThread = [None]

def _delimLoop():
    while True:
        _delimEvent.wait()
        _delimEvent.clear()
        while True:
            rest = 0.5 - (time.time() - _delimLast[0])
            if rest <= 0:
                break
            time.sleep(rest)
        safe_print(colored('-'*80, 'grey'))

def delimiter():
    _delimLast[0] = time.time()
    if _delimThread[0] is None:
        try:
            t = threading.Thread(target=_delimLoop, name='log-delimiter', daemon=True)
            t.start()
            _delimThread[0] = t
        except RuntimeError:
            return              # no thread available right now: no delimiter, no harm
    _delimEvent.set()


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

        
