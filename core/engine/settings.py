from ..module import Module
import json
import os

class Settings(Module):

    _ready = False
    _settingspath = None
    _settings = {
        'flip':         False,
        'autoplay':     False,
        'loop':         0,              # -1: only one no loop / 0: playlist no loop / 1: loop one / 2: loop all
        'volume':       100,
        'mute':         False,
        'audioout':     'jack',
        'audiomode':    'stereo',
        'pan':          [100,100],
        'playlist':     None, 
        'brightness':   100,
        'contrast':     50
    }

    def __init__(self, hplayer, persistent=None):
        super().__init__(hplayer, 'Settings', 'yellow')     
        
        self._settingspath = persistent

        # Autobind to player
        hplayer.autoBind(self)


    def __call__(self, entry=None):
        if entry:
            return self.export()[entry]
        else:
            return self.export()


    def load(self, persistent=None):

        if persistent:
            self._settingspath = persistent

        if not self._settingspath:
            self.log('no settings file defined')
            return
        
        if self._settingspath and os.path.isfile(self._settingspath):
            try:
                with open(self._settingspath, 'r') as fd:
                    loaded = json.load(fd)
                    for key in loaded:
                        if key in self._settings:
                            self._settings[key] = loaded[key]
                self.emit('loading')
                for key in self._settings:
                    self.emit('do-'+key, self._settings[key], self.export())
                self.emit('updated', self.export())
                self.emit('loaded', self.export())
                self.log('settings loaded:', self._settings)
            except:
                self.log('ERROR loading settings file', self._settingspath)  

        self._ready = True


    def export(self):
        return self._settings.copy()


    def get(self, key):
        if key in self._settings:
            return self._settings[key]
        return None


    def set(self, key, val):
        if not self._ready:
            self.log('WARNING: settings not ready to set', key, val)
            return
        if not key in self._settings:
            self._settings[key] = None
        if self._settings[key] != val:
            self._settings[key] = val
            self.emit('do-'+key, val, self.export())
            self.emit('updated', self.export())
            self.save()


    def save(self):
        if self._settingspath:
            with open(self._settingspath, 'w') as fd:
                json.dump(self._settings, fd, indent=4)
