import json
import os

from ..module import Module

# SURFACE — the LED / output transform of the video player, persisted with the other
# settings and edited live from http2 (kmini minis: the mpv GLSL scaler, 03-scaler.glsl).
# `enable: False` = the transform is bypassed (plain full-screen output).
SURFACE_DEFAULTS = {
    'enable':           False,
    'width':            0,          # target block in output pixels, 0 = source size
    'height':           0,
    'rotate':           0.0,        # degrees, any angle
    'halfheight':       False,      # even-line LED panels: squash the block to half height
    'fit':              'cover',    # cover | contain | stretch
    'align':            'center',   # center | left  (horizontal crop / content alignment)
    'source_offset_x':  0,
    'source_offset_y':  0,
    'output_x':         0,          # where the finished block lands on the output
    'output_y':         0,
}
SURFACE_FIT = ('cover', 'contain', 'stretch')
SURFACE_ALIGN = ('center', 'left')


def clean_surface(surface):
    """Coerce a (partial) surface dict onto SURFACE_DEFAULTS: bad values fall back to the
    default rather than raising — a slider on a phone must never break the player."""
    src = surface if isinstance(surface, dict) else {}
    out = {}
    for key, default in SURFACE_DEFAULTS.items():
        val = src.get(key, default)
        try:
            if isinstance(default, bool):
                if not isinstance(val, bool):
                    val = str(val).lower() in ('1', 'true', 'yes', 'on')
            elif isinstance(default, float):
                val = float(val)
            elif isinstance(default, int):
                val = int(float(val))
            else:
                val = str(val).lower()
        except (TypeError, ValueError):
            val = default
        out[key] = val
    if out['fit'] not in SURFACE_FIT:
        out['fit'] = SURFACE_DEFAULTS['fit']
    if out['align'] not in SURFACE_ALIGN:
        out['align'] = SURFACE_DEFAULTS['align']
    return out


class Settings(Module):

    _ready = False
    _settingspath = None
    _settings = {
        'flip':         False,
        'autoplay':     False,
        'loop':         0,              # -1: only one no loop / 0: playlist no loop / 1: loop one / 2: loop all
        'volume':       100,
        'mute':         False,
        'audiomode':    'stereo',
        'pan':          [100,100],
        'playlist':     None, 
        'brightness':   100,
        'contrast':     50,
        'filter':       '',
        'surface':      None            # see SURFACE_DEFAULTS; None = never set (bypass)
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

        loaded_from_file = False

        if not self._settingspath:
            self.log('no settings file defined; using default values')
        
        elif os.path.isfile(self._settingspath):
            try:
                with open(self._settingspath, 'r') as fd:
                    loaded = json.load(fd)
                    for key in loaded:
                        if key in self._settings:
                            self._settings[key] = loaded[key]
                loaded_from_file = True
            except:
                self.log('ERROR loading settings file', self._settingspath)  
        else:
            self.log('settings file not found, using default values', self._settingspath)

        self._ready = True

        snapshot = self.export()
        self.emit('loading')
        for key in self._settings:
            self.emit('do-'+key, self._settings[key], snapshot)
        self.emit('updated', snapshot)
        self.emit('loaded', snapshot)

        if loaded_from_file:
            self.log('settings loaded:', self._settings)
        else:
            self.log('settings ready (defaults):', self._settings)


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
        if key not in self._settings:
            self._settings[key] = None
        if self._settings[key] != val:
            self._settings[key] = val
            self.emit('do-'+key, val, self.export())
            self.emit('updated', self.export())
            self.save()
            
    def update(self):
        if self._ready:
            self.emit('updated', self.export())

    def save(self):
        if self._settingspath:
            with open(self._settingspath, 'w') as fd:
                json.dump(self._settings, fd, indent=4)
