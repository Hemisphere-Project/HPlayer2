from .mpv import MpvPlayer

class MpvstreamPlayer(MpvPlayer):
    def __init__(self, hplayer, name):
        super().__init__(hplayer, name)
        
        self._mpv_command += [  '--rtsp-transport=udp'
                                ,'--no-cache'
                                # ,'--untimed'
                                ,'--no-correct-pts'
                                ,'--framedrop=vo'
                                ,'--profile=low-latency'
                                , '--framedrop=vo'
                                ]
        
        self._validExt = ['rtsp://', 'rtmp://', 'http://', 'https://'] 