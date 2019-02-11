import sys
import time
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

def do(arg):
    print (arg)
    
def undo(arg):
    print ('undo', arg)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    path = '/dev/input/'
    event_handler = FileSystemEventHandler()
    event_handler.on_created = do
    event_handler.on_deleted = undo
    observer = Observer()
    observer.schedule(event_handler, path, recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
