"""
Conduite: a tiny text cue-language for DMX, evaluated as a pure function of time.

A conduite is a plain-text score that sits next to its media as a sidecar file
(vague.mp4 -> vague.dmx). Each line is either a directive or a cue:

    # comment / blank lines ignored

    def wash    1-4          # alias: a name -> a channel, range or list
    def strobe  8

    # <time>   <target> [<target> ...]   [fade <sec>]
    0:00   wash@0                        # blackout on start
    0:03   wash@255        fade 3        # fade up over 3s
    0:12   wash@80 strobe@255            # snap (no fade)
    0:20   strobe@0 wash@40   fade 5     # slow settle
    1:00   wash@0          fade 8        # fade out

Rules, kept deliberately small:
  - time     : M:SS, M:SS.mmm, H:M:S or bare seconds (12, 12.5). It is when the
               transition STARTS; `fade N` is how long it takes to arrive
               (target reached at time+N). No fade = instant snap.
  - target   : <channels>@<value>[/<fade>]
  - channels : single `1`, range `1-4`, list `1,3,5`, or a `def` alias
  - value    : 0..255, or a percentage `50%`. Held until the next cue touches it.
  - /<fade>  : per-channel fade override in seconds (differs from the cue fade)

The whole point: output level is a pure function level(channel, t). Recomputed
every frame from the player's (synced) clock, DMX stays correct through seeks,
loops, pause and multi-device wall-sync with zero extra networking. Fades are
just interpolation between the two cues that bracket t.
"""

UNIVERSE = 512


class Conduite:

    def __init__(self, text=''):
        self.aliases = {}        # name -> [channel, ...]
        self.errors = []         # [(lineno, message), ...]
        self._keys = {}          # channel -> [(time, target, fade), ...] time-ordered
        self.maxtime = 0.0       # last cue end, for UI scrubbing
        if text:
            self.parse(text)

    #
    # PARSING
    #

    def parse(self, text):
        self.aliases = {}
        self.errors = []
        cues = []                # [(time, [(channels, value, fade), ...]), ...]

        for lineno, raw in enumerate(text.splitlines(), 1):
            line = raw.split('#', 1)[0].strip()
            if not line:
                continue
            tok = line.split()

            try:
                if tok[0] == 'def':
                    if len(tok) < 3:
                        raise ValueError("usage: def <name> <channels>")
                    self.aliases[tok[1]] = self._channels(tok[2])
                    continue

                # cue line: <time> targets... [fade N]
                t = self._time(tok[0])
                fade = 0.0
                sets = []
                i = 1
                while i < len(tok):
                    w = tok[i]
                    if w == 'fade':
                        if i + 1 >= len(tok):
                            raise ValueError("`fade` needs a duration")
                        fade = self._seconds(tok[i + 1])
                        i += 2
                        continue
                    if '@' not in w:
                        raise ValueError("expected <channels>@<value>, got '%s'" % w)
                    chanpart, valpart = w.split('@', 1)
                    ov = None
                    if '/' in valpart:
                        valpart, fadepart = valpart.split('/', 1)
                        ov = self._seconds(fadepart)
                    sets.append((self._channels(chanpart), self._value(valpart), ov))
                    i += 1
                cues.append((t, fade, sets))
            except (ValueError, KeyError) as e:
                self.errors.append((lineno, str(e)))

        self._compile(cues)

    def _compile(self, cues):
        # flatten cues into per-channel time-ordered keyframes
        self._keys = {}
        self.maxtime = 0.0
        for t, fade, sets in sorted(cues, key=lambda c: c[0]):
            for channels, value, ov in sets:
                f = ov if ov is not None else fade
                self.maxtime = max(self.maxtime, t + f)
                for ch in channels:
                    self._keys.setdefault(ch, []).append((t, value, f))
        for ch in self._keys:
            self._keys[ch].sort(key=lambda k: k[0])

    #
    # token helpers
    #

    def _channels(self, spec):
        if spec in self.aliases:
            return list(self.aliases[spec])
        out = []
        for part in spec.split(','):
            if '-' in part:
                a, b = part.split('-', 1)
                lo, hi = int(a), int(b)
                if lo > hi:
                    lo, hi = hi, lo
                out.extend(range(lo, hi + 1))
            else:
                out.append(int(part))
        for ch in out:
            if not 1 <= ch <= UNIVERSE:
                raise ValueError("channel %d out of range 1..%d" % (ch, UNIVERSE))
        return out

    def _value(self, v):
        if v.endswith('%'):
            pct = float(v[:-1])
            n = round(pct / 100.0 * 255)
        else:
            n = int(v)
        return max(0, min(255, n))

    def _seconds(self, s):
        f = float(s)
        if f < 0:
            raise ValueError("negative duration")
        return f

    def _time(self, s):
        parts = s.split(':')
        if len(parts) == 1:
            return self._seconds(parts[0])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        raise ValueError("bad time '%s'" % s)

    #
    # EVALUATION
    #

    def level(self, channel, t):
        """DMX value 0..255 of one channel at time t (seconds)."""
        kfs = self._keys.get(channel)
        if not kfs:
            return 0
        prev = 0.0
        val = 0.0
        for ktime, target, fade in kfs:
            if t < ktime:
                break
            if fade > 0 and t < ktime + fade:
                val = prev + (target - prev) * (t - ktime) / fade
            else:
                val = target
            prev = target
        return int(round(max(0, min(255, val))))

    def frame(self, t):
        """Full universe as a bytearray(512) at time t."""
        out = bytearray(UNIVERSE)
        for ch in self._keys:
            out[ch - 1] = self.level(ch, t)
        return out

    def activeChannels(self):
        """Channels this conduite ever touches (sorted), for a compact UI meter."""
        return sorted(self._keys.keys())
