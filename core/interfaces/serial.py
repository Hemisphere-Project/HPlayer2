from .serialbase import SerialBase


class SerialInterface (SerialBase):

    def  __init__(self, hplayer, filter="", maxRetry=0):
        super().__init__(hplayer, "Serial", filter, dtrReset=True, maxRetry=maxRetry, scanInterval=5.0)

    # '/topic arg1 arg2' lines -> emit('topic', 'arg1', 'arg2')
    def onLine(self, line):
        data = line.split(' ')
        data[0] = data[0].lower()
        if data[0][0] == '/':  # Serial message must start with a slash
            data[0] = data[0][1:]
            data[0].replace('/','.')
            self.emit(data[0], *data[1:])
