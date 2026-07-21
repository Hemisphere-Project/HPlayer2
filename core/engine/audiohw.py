"""Contract with the platform's audio plumbing (Pi-tools `audiohub` module).

Dedicated player images carry /etc/audiohub.conf (installed by the Pi-tools
module), optionally overridden by /data/audiohub.conf (user/app-writable on a
read-only rootfs; later file wins). The file's presence means the always-on
multi-output hub is running — HPlayer2 then targets the alsa/hplayer PCM and
compensates the forwarder latency. Without it, HPlayer2 uses the default
ALSA environment and never touches audio configuration (laptop / dev case).
"""

AUDIO_CONF_PATHS = ('/etc/audiohub.conf', '/data/audiohub.conf')


def read_audio_conf(paths=AUDIO_CONF_PATHS):
    """Parse the platform audio contract (merged, later file wins).

    Returns {'graph': str|None, 'latency_us': int} when at least one file
    exists, None when the platform is generic (no hub).
    """
    if isinstance(paths, str):
        paths = (paths,)

    conf = None
    for path in paths:
        try:
            with open(path) as fd:
                text = fd.read()
        except OSError:
            continue
        if conf is None:
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
