from __future__ import print_function
from termcolor import colored
from base import BaseInterface

import kpimsg as km
import json
import msgpack

class KmsgInterface (BaseInterface):

    def  __init__(self, player, args):

        if len(args) < 1:
            args.append('kmsg')

        super(KmsgInterface, self).__init__(player)

        self.name = args[0]
        self.nameP = colored(self.name,'blue')

        self.portKpi = 8002

        km.set_app_name("kplayer")
        km.start_gateway(1000)

        ep = km.Endpoint(self.name, port=self.portKpi)
        ep.set_callback(self.kpi_receive, None)
        ep.start()

        print(self.nameP, "started on", "kplayer/"+self.name )

        self.start()


    # Kpi send
    def emit(self, path, *args):
        #  Emit KPI msg
        print(self.nameP, "sent KpiMSG", path, args )

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
