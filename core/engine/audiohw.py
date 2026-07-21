"""Contract with the platform's audio plumbing (Pi-tools `hplayer-audio`).

Dedicated player images carry /etc/hplayer-audio.conf (installed by the
Pi-tools module): its presence means the always-on multi-output hub is
running — HPlayer2 then targets the alsa/hplayer PCM and compensates the
forwarder latency. Without the file, HPlayer2 uses the default ALSA
environment and never touches audio configuration (laptop / dev case).
"""

AUDIO_CONF = '/etc/hplayer-audio.conf'


def read_audio_conf(path=AUDIO_CONF):
    """Parse the platform audio contract.

    Returns {'graph': str|None, 'latency_us': int} when the file exists,
    None when the platform is generic (no hub).
    """
    try:
        with open(path) as fd:
            text = fd.read()
    except OSError:
        return None

    conf = {'graph': None, 'latency_us': 30000}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, val = (s.strip() for s in line.split('=', 1))
        if key == 'graph':
            conf['graph'] = val
        elif key == 'latency_us':
            try:
                conf['latency_us'] = int(val)
            except ValueError:
                pass
    return conf
