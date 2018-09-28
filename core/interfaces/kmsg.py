from .base import BaseInterface

import kpimsg as km
import json
import msgpack

class KmsgInterface (BaseInterface):

    def  __init__(self, player):
        super(KmsgInterface, self).__init__(player, "KMSG")

        self._portKpi = 8002

        km.set_app_name("kplayer")
        km.start_gateway(1000)

        self.ep = km.Endpoint(self.name, port=self._portKpi)
        self.ep.set_callback(self.kpi_receive, None)
        self.ep.start()

        self.player.on(['*'], self.emit)

        self.log("started on", "kplayer/"+self.name )

    # Listener
    def listen(self):
        self.stopped.wait()

    # Kpi send
    def emit(self, event, args):
        DATA_FORMAT = km.FORMAT_DATA_MSGPACK

        # serialize
        if (DATA_FORMAT == km.FORMAT_DATA_MSGPACK):
            k_args = msgpack.packb(args)
        elif (DATA_FORMAT == km.FORMAT_DATA_JSON):
            k_args = json.dumps(args, separators=(',',':'))
        else:
            k_args = ' '.join(args)

        self.ep.emit("/event/"+event, k_args, DATA_FORMAT)

        #  Emit KPI msg
        self.log("KPimsg emit: ", "/event/"+event, args )

    # Kpi receiver
    def kpi_receive(self, msg, data):

        # parse data
        if (msg.format == km.FORMAT_DATA_MSGPACK):
            args = msgpack.unpackb(msg.data.tobytes())
        elif (msg.format == km.FORMAT_DATA_JSON):
            args = json.loads(msg.data.tobytes())

        # convert dict to list
        if isinstance(args,dict):
            args = data.values()

        if msg.path == "/play":
            self.player.loop(False)
            if args[0]: self.player.play(args[0])
            else: self.player.play()

        elif msg.path == "/playloop":
            self.player.loop(True)
            if args[0]: self.player.play(args[0])
            else: self.player.play()

        elif msg.path == "/load":
            self.player.load(args[0])

        elif msg.path == "/stop":
            self.player.stop()

        elif msg.path == "/pause":
            self.player.pause()

        elif msg.path == "/resume":
            self.player.resume()

        elif msg.path == "/next":
            self.player.next()

        elif msg.path == "/prev":
            self.player.prev()

        elif msg.path == "/loop":
            self.player.loop(True)

        elif msg.path == "/unloop":
            self.player.loop(False)

        elif msg.path == "/volume":
            self.player.volume(args[0])

        elif msg.path == "/mute":
            self.player.mute(True)

        elif msg.path == "/unmute":
            self.player.mute(False)

        elif msg.path == "/flip":
            self.player.flip(True)

        elif msg.path == "/unflip":
            self.player.flip(False)

        elif msg.path == "/status":
            print('STATUS')
            pass

        elif msg.path == "/quit":
            self.isRunning(False)

        # info
        # print("KPIMSG received '%s' '%s' " % (msg.path, msg.data.tobytes()))
