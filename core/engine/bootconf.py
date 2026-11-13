"""The player's role, read from /boot/hplayer2.conf.

One base image, roles by files on /boot (RastaOS-7.5): what used to be a constant or a
/boot/wifi marker test inside a per-site profile is a key in this file, so a card is
re-roled by editing /boot, never by shipping code.

    # /boot/hplayer2.conf
    [player]
    profile = biennale          ; used when the service passes no profile

    [sync]
    iface = eth0                ; eth0 | wlan0 | wlan1 | wint | auto | none
    role  = master              ; master | slave | elected | none
    wall  = yes                 ; WALL_SYNC: continuous frame-lock (wallclock + chase)

    [schedule]
    enabled     = yes
    require_rtc = yes           ; gate only with a real clock

    [interfaces]
    keypad  = no
    teleco2 = no
    nowde   = no

An ABSENT file is not an error: `present` is False and every accessor returns the
default the caller passes, so a profile that asks keeps its old behaviour on a card
that has no conf. A malformed file is reported and read as absent — boot never stops
on a typo in /boot.
"""

import configparser
import os

DEFAULT_PATH = '/boot/hplayer2.conf'
ENV_PATH = 'HPLAYER2_CONF'                 # dev/test override of the path

ROLES = ('master', 'slave', 'elected')
IFACES_AUTO = ('wint', 'eth0', 'wlan0', 'wlan1')

_TRUE = ('1', 'yes', 'true', 'on')
_FALSE = ('0', 'no', 'false', 'off', '')


class BootConf:

    def __init__(self, path=None):
        self.path = path or os.environ.get(ENV_PATH) or DEFAULT_PATH
        self.present = False
        self.errors = []
        self._cp = configparser.ConfigParser(inline_comment_prefixes=(';', '#'),
                                             interpolation=None)
        if not os.path.isfile(self.path):
            return
        try:
            with open(self.path, encoding='utf-8') as f:
                self._cp.read_file(f, source=self.path)
            self.present = True
        except (configparser.Error, OSError, UnicodeDecodeError) as e:
            self.errors.append(str(e).splitlines()[0])
            self._cp = configparser.ConfigParser(interpolation=None)
            print('[bootconf] ' + self.path + ' unreadable, ignored: ' + self.errors[-1])

    # --- raw accessors -------------------------------------------------------------

    def get(self, section, key, default=None):
        """The stripped string value, or `default` when the section/key is absent."""
        if not self._cp.has_option(section, key):
            return default
        return self._cp.get(section, key).strip()

    def flag(self, section, key, default=False):
        """A yes/no key. An unparseable value keeps `default` and is reported."""
        v = self.get(section, key)
        if v is None:
            return default
        v = v.lower()
        if v in _TRUE:
            return True
        if v in _FALSE:
            return False
        self.errors.append('%s.%s: not a yes/no value: %r' % (section, key, v))
        print('[bootconf] ' + self.errors[-1] + ' — keeping ' + str(default))
        return default

    # --- the role --------------------------------------------------------------------

    def profile(self, default=None):
        return self.get('player', 'profile', default) or default

    def sync_role(self, default=None):
        """'master' | 'slave' | 'elected', or None when this player does not sync."""
        v = self.get('sync', 'role')
        if v is None:
            return default
        v = v.lower()
        if v in ROLES:
            return v
        if v not in ('none', 'off', 'no', ''):
            self.errors.append('sync.role: unknown role %r' % v)
            print('[bootconf] ' + self.errors[-1] + ' — sync off')
        return None

    def sync_iface(self, has_interface=None, default=None):
        """The sync interface name, or None for none.

        `auto` (or an absent key while a role is set) picks the first of wint, eth0, wlan0,
        wlan1 that `has_interface` reports — the order the live profiles already use.
        """
        v = self.get('sync', 'iface')
        if v is None:
            if self.sync_role() is None:
                return default
            v = 'auto'
        v = v.lower()
        if v in ('none', 'off', 'no', ''):
            return None
        if v != 'auto':
            return v
        if has_interface is None:
            from core.engine import network
            has_interface = network.has_interface
        for iface in IFACES_AUTO:
            if has_interface(iface):
                return iface
        return None

    def wall_sync(self, default=False):
        return self.flag('sync', 'wall', default)


def load(path=None):
    return BootConf(path)
