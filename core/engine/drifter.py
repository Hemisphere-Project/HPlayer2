from termcolor import colored
from collections import deque
from statistics import median
import math
import time
import datetime


#
#  Chase-lock speed servo
#
#  Keeps a media player aligned on an external clock by adjusting its
#  playback speed, with a hard seek when the gap is beyond servo reach.
#  Clock-source agnostic: whoever owns a clock (wallclock UDP, MTC, OSC..)
#  calls tick(clock) at its own cadence.
#
#  Servo logic ported from the Nowde MTC tracker (core/interfaces/nowde.py
#  on master): dead zone with hysteresis, progressive speed curve, weighted
#  speed smoothing. Added here: wrap-aware diff for looping media.
#
class Drifter():

    def __init__(self, player, log=None,
                    deadZoneEnter=0.025,    # s - enter dead zone (+-0.75 frame @30fps)
                    deadZoneExit=0.08,      # s - exit dead zone (hysteresis)
                    seekThreshold=2.0,      # s - hard seek when this far AHEAD (and, by default, behind)
                    seekLateThreshold=None, # s - hard seek when this far LATE; None = symmetric (= seekThreshold)
                    jumpFix=500,            # ms - added to seek target (seek latency compensation)
                    smoothingWindow=3,      # speed weighted-moving-average window
                    kickStartGrace=20,      # ticks of grace after (re)play
                    danceMode=False,        # jump-ahead + pause + timed resume instead of blind jumps
                    danceMargin=2.0):       # s - wait budget ahead of the estimated seek landing

        self.player = player
        self.log = log if log else print

        self.deadZoneEnter = deadZoneEnter
        self.deadZoneExit = deadZoneExit
        self.seekThreshold = seekThreshold
        # Late tolerance may exceed the ahead tolerance: a late player ramps
        # speed to catch up until seekLateThreshold, then hard-seeks. Default
        # (None) is symmetric, so the wallclock servo stays unchanged.
        self.seekLateThreshold = seekLateThreshold if seekLateThreshold is not None else seekThreshold
        self.jumpFix = jumpFix
        self.smoothingWindow = smoothingWindow
        self.kickStartGrace = kickStartGrace

        # Servo state (same semantics as the nowde tracker)
        self.lastSpeed = 1.0
        self.lastPos = -1
        self.didJump = False
        self.kickStart = 0
        self.speedHistory = []
        self.inDeadZone = False

        self.doLog = True
        self.onStalled = None   # optional hook: player not playing after grace (nowde plugs pattern-replay here)

        # Chase lead (s): the player timeline runs this far AHEAD of the shared
        # clock. Used with the audio hub: timeline leads by the pipeline
        # latency while mpv delays video by the same amount, so both the
        # frames on screen and the audio at the speakers land exactly on the
        # wallclock — mixed fleets (hub and non-hub players) stay aligned.
        self.offset = 0.0

        # ── Smart join (danceMode) ──────────────────────────────────────
        # Benchmarked 2026-07-23 (extra/bench: N100/vaapi + RPi/mmal, GOP
        # 1s..single-keyframe): keyframe-mode seeks are instant but land a
        # full GOP away (median 1.2–4.2s, worst 42s) — the historic join
        # chaos. EXACT seeks land within a constant ~0.22s on BOTH
        # platforms; their cost is decode-bound: negligible on vaapi
        # (≤0.5s worst), GOP-proportional on mmal (0.4s@1s-GOP → 8s on
        # single-keyframe). Strategy: exact seek to clock + LEARNED seek
        # latency; measure the landing error at the first moving tick and
        # fold it back (EMA) — the second seek lands in servo range on any
        # platform × content, and the capped ramp trims the rest.
        self.danceMode = danceMode
        self.danceMargin = danceMargin
        self._seekLatEst = 0.35               # s, EMA of measured seek cost (incl. the ~0.22s restart bias)
        self._pendingJump = None

        # Median filter on the measured diff: wifi delivery jitter swings
        # the raw per-packet diff by +-30ms, which stalls dead-zone entry
        # (true -0.04 reads -0.03..-0.09) and causes spurious exits.
        # 5 ticks @20Hz = 250ms of control lag, negligible vs servo time
        # constants. Cleared on jump/arm so the post-jump landing
        # measurement stays a single fresh sample.
        self._diffWindow = deque(maxlen=5)

    # Reset servo state + grace period: call on every new play
    def arm(self):
        self.kickStart = self.kickStartGrace
        self.didJump = False
        self.speedHistory = []
        self.inDeadZone = False
        self.lastPos = -1
        self.lastSpeed = 1.0
        self._diffWindow.clear()
        # Keep a FRESH in-flight jump measurement: mpv emits 'playing'
        # (core-idle flip) right after the play that triggered the jump,
        # and profiles re-arm on that event — wiping the measurement here
        # would lose the seek-latency learning on every join. A genuinely
        # new play >2s later still discards the stale jump.
        if self._pendingJump is not None and time.time() - self._pendingJump['t0'] > 2.0:
            self._pendingJump = None

    # Freewheel: back to speed 1.0, clear servo state (clock lost / master gone)
    def release(self):
        if self.lastSpeed != 1.0:
            self.player.speed(1.0)
            self.lastSpeed = 1.0
        self.speedHistory = []
        self.inDeadZone = False
        self.lastPos = -1
        self.kickStart = 0
        self._diffWindow.clear()
        # A pending jump measurement survives freewheel: brief clock
        # dropouts (RF churn) must not lose the seek-latency learning.

    # ── Smart jump (danceMode) ──────────────────────────────────────────
    # EXACT seek to clock + learned latency; measure the landing at the
    # first moving tick and fold it back. Keyframe-mode jumps land a full
    # GOP away (benchmarked: median 1.2–4.2s, worst 42s) — exact seeks
    # land within ~0.22s constant, cost decode time that this estimator
    # learns per session.

    def _smartJump(self, clock, diff, duration):
        target = clock + self._seekLatEst
        if duration and duration > 3:
            target = target % duration
        self._pendingJump = {'t0': time.time()}
        self._diffWindow.clear()
        if self.doLog:
            self.log("timedelay=" + colored(round(diff, 2), "red"),
                     "JUMP exact to %.1fs (seekLat~%.2fs)" % (target, self._seekLatEst))
        self.player.seekTo(target * 1000, exact=True)
        self.didJump = True
        return {'diff': diff, 'speed': self.lastSpeed, 'jumped': True, 'locked': False}

    # One servo step against the estimated master clock (s, media timeline).
    # duration (s): enables wrap arithmetic on looping media (0 = unknown).
    # Returns telemetry dict, or None if the tick was dropped.
    def tick(self, clock, duration=0):

        clock = clock + self.offset

        pos = self.player.position()

        # Resume if paused
        if self.player.isPaused():
            self.player.resume()

        # Player has been launched, wait for it to start
        if self.kickStart > 0:
            self.kickStart -= 1

        # Player is stopped
        elif not self.player.isPlaying():
            if self.kickStart < 0:
                self.kickStart += 1
            else:
                if self.onStalled:
                    self.onStalled()
                    self.kickStart = self.kickStartGrace
                return None
        else:
            self.kickStart = -3

        # Check if player time is actually ellapsing
        if pos == self.lastPos or not self.player.isPlaying():
            if self.doLog and self.kickStart == 0:
                self.log("no news from player.. dropping clock tracking on this tick")
            return None
        self.lastPos = pos

        diff = clock - pos

        # Wrap-aware shortest path: on looping media the clock and the player
        # wrap independently; +-duration jumps around the loop point are not
        # desyncs. Skip on very short / unknown durations.
        if duration and duration > 3:
            diff = ((diff + duration / 2) % duration) - duration / 2

        # De-jitter: servo on the median of recent diffs (see __init__).
        self._diffWindow.append(diff)
        diff = median(self._diffWindow)

        speed = 1.0
        fix = 0     # latency corrector (clock source to tracker), kept from nowde
        jumped = False

        # Landing measurement (danceMode): the first moving ticks after a
        # jump carry the seek's residual error — learn from the median of
        # the first 3 (the very first tick reads mpv's optimistic
        # post-restart time-pos, benchmarked as a spurious outlier).
        # Learn BEFORE the threshold decision, because on slow-seek content
        # the landing can itself be beyond threshold (mmal mire: +3.9s
        # after a 4s seek) and the next jump must aim with the updated
        # estimate, or the chain never converges.
        if self._pendingJump is not None and len(self._diffWindow) >= 3:
            landing = median(self._diffWindow)
            self._seekLatEst = min(30.0, max(0.05, self._seekLatEst + 0.7 * landing))
            if self.doLog:
                self.log("JUMP landed %+.2fs off, seekLat now %.2fs" % (landing, self._seekLatEst))
            self._pendingJump = None

        # Hard seek: desync beyond servo reach. Asymmetric: a late player
        # (diff > 0) is tolerated up to seekLateThreshold; ahead uses seekThreshold.
        # Never re-jump while a landing measurement is pending: the next
        # jump must aim with the updated estimate (danceMode chain).
        if (diff > self.seekLateThreshold or diff < -self.seekThreshold) \
                and not (self.danceMode and self._pendingJump is not None):
            if self.danceMode:
                return self._smartJump(clock, diff, duration)
            target = clock + self.jumpFix / 1000.0
            if duration and duration > 3:
                target = target % duration
            self.player.seekTo(target * 1000)
            self.didJump = True
            jumped = True
            if self.doLog:
                self.log("timedelay=" + colored(round(diff, 2), "red"), "JUMP (fix " + str(self.jumpFix) + "ms)")

        else:
            # Jump correction
            if self.didJump:
                self.didJump = False
                self.speedHistory = []
                self.inDeadZone = False

            # Dead zone with hysteresis to prevent oscillation
            currentOffset = abs(diff + fix)
            applyCorrection = True

            if self.inDeadZone:
                if currentOffset > self.deadZoneExit:
                    self.inDeadZone = False
                    applyCorrection = True
                else:
                    speed = 1.0
                    applyCorrection = False
            else:
                if currentOffset <= self.deadZoneEnter:
                    speed = 1.0
                    self.inDeadZone = True
                    applyCorrection = False
                else:
                    applyCorrection = True

            if applyCorrection:
                # When late: progressive acceleration
                if (diff + fix) > 0:
                    # Ramp ceiling 2.0: benchmarked 2026-07-23 — mmal
                    # saturates at ~2x realtime (a commanded 8x plays 2x),
                    # and with exact-seek jumps nothing needs to sprint.
                    if diff > 3.0:
                        speed = 2.0
                    elif diff > 1.5:
                        speed = round(1 + (diff + fix) * 2.0, 2)
                        speed = min(speed, 2.0)
                    elif diff > 0.8:
                        speed = round(1 + (diff + fix) * 1.5, 2)
                        speed = min(speed, 2.0)
                    elif diff > 0.4:
                        speed = round(1 + (diff + fix) * 1.2, 2)
                        speed = min(speed, 2.0)
                    elif diff > 0.2:
                        speed = round(1 + (diff + fix) * 0.5, 2)
                        speed = min(speed, 1.15)
                    else:
                        speed = round(1 + (diff + fix) * 0.25, 3)
                        speed = min(speed, 1.05)

                # When ahead: progressive deceleration, very gentle near lock
                elif (diff + fix) < 0:
                    if diff < -1.5:
                        speed = 0.2
                    elif diff < -0.8:
                        speed = round(1 + (diff + fix) * 2.0, 2)
                        speed = max(speed, 0.3)
                    elif diff < -0.4:
                        speed = round(1 + (diff + fix) * 1.5, 2)
                        speed = max(speed, 0.5)
                    elif diff < -0.2:
                        speed = round(1 + (diff + fix) * 1.0, 2)
                        speed = max(speed, 0.8)
                    elif diff < -0.08:
                        speed = round(1 + (diff + fix) * 0.3, 2)
                        speed = max(speed, 0.95)   # 0.975 made the post-jump tail crawl (~5s for 0.1s)
                    else:
                        speed = round(1 + (diff + fix) * 0.15, 3)
                        speed = max(speed, 0.99)

                # Speed smoothing to reduce oscillation
                self.speedHistory.append(speed)
                if len(self.speedHistory) > self.smoothingWindow:
                    self.speedHistory.pop(0)

                # Weighted average favoring recent values (skip in extreme situations)
                if len(self.speedHistory) >= 2 and abs(diff) < 1.0:
                    weights = [i + 1 for i in range(len(self.speedHistory))]
                    smoothed = sum(s * w for s, w in zip(self.speedHistory, weights)) / sum(weights)
                    speed = round(smoothed, 3)   # 2-decimal rounding parked sub-0.07s residuals at speed 1.0
            else:
                # In dead zone: clear history for a fresh start when exiting
                if len(self.speedHistory) > 0:
                    self.speedHistory = []

        self.player.speed(speed)

        # LOG
        if self.doLog:
            if speed != 1.0 or self.lastSpeed != 1.0:
                timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]

                color1 = 'green'
                if abs(diff + fix) > 0.08: color1 = 'red'
                elif abs(diff + fix) > 0.04: color1 = 'yellow'

                color2 = 'white'
                if speed > 1: color2 = 'magenta'
                elif speed < 1: color2 = 'cyan'

                framedelta = math.trunc(diff * 1000 / 30)
                color3 = 'green'
                if abs(framedelta) > 1: color3 = 'red'
                elif abs(framedelta) > 0: color3 = 'yellow'

                self.log("[" + timestamp + "]",
                            "timedelay=" + colored(round(diff, 2), color1),
                            "framedelta=" + colored(framedelta, color3),
                            "speed=" + colored(speed, color2))

        telemetry = {'diff': diff, 'speed': speed, 'jumped': jumped, 'locked': self.inDeadZone}
        self.lastSpeed = speed
        return telemetry
