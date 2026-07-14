from core.engine.hplayer import HPlayer2

# EXTRA TMP UPLOAD
import tempfile
tempfile.tempdir = '/data/var/tmp'


# Dispositif C, Biennale 2026: outdoor audio player triggered by radar proximity.
# An ESP32-C3 + LD2450 box (extra/arduino/radar_c3) plugs in over USB and streams raw
# targets; the `radar` interface does all the gating. Playback is optionally restricted
# to a daily window by the generic `schedule` interface (RTC on the Pi keeps time offline).

# MEDIA PATH
mediaPath = ['/data/media', '/data/usb']

# INIT HPLAYER
hplayer = HPlayer2(mediaPath, '/data/hplayer2-biennale26-radar.cfg')

# PLAYER
player = hplayer.addPlayer('mpv', 'player')
player.doLog['events'] = True
player.doLog['cmds'] = False

# INTERFACES
hplayer.addInterface('http2', 80, {'playlist': False, 'loop': False, 'mute': True})
radar = hplayer.addInterface('radar')       # USB, auto-discovered
schedule = hplayer.addInterface('schedule')  # daily play window (disabled by default)


# Keep the playlist in sync with the media folder
@hplayer.on('app-run')
@hplayer.on('files.filelist-updated')
def build_list(ev=None, *args):
    hplayer.playlist.load(hplayer.files.currentList())


# TRIGGER: on entry, play the piece once — but only inside the schedule window, and
# never while something is already playing (play-out). Because the radar only re-emits
# `enter` after a `leave`, a visitor who lingers hears it once; one who leaves and comes
# back after it ended re-triggers.
@hplayer.on('radar.enter')
def onEnter(ev, *args):
    if schedule.isOpen() and not player.isPlaying():
        hplayer.settings.set('loop', -1)     # play a single media, then idle
        hplayer.playlist.play()


@hplayer.on('schedule.close')
def onClose(ev, *args):
    player.stop()                            # go silent when the window closes


# Persist radar + schedule tunables edited from the http2 web UI (interfaces read live)
for key in ('radar-range', 'radar-width', 'radar-enter-ms', 'radar-leave-ms',
            'schedule-enable', 'schedule-open', 'schedule-close'):
    hplayer.on('http2.' + key)(lambda ev, *a, k=key: hplayer.settings.set(k, a[0]))


# HTTP2 log panel
@hplayer.on('player.*')
@hplayer.on('radar.*')
@hplayer.on('schedule.*')
def http2_logs(ev, *args):
    if len(args) and args[0] == 'time':
        return
    hplayer.interface('http2').send('logs', [ev] + list(args))


# RUN
hplayer.run()
