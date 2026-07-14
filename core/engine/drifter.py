from termcolor import colored
import math
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
                    seekThreshold=2.0,      # s - |diff| beyond this -> hard seek
                    jumpFix=500,            # ms - added to seek target (seek latency compensation)
                    smoothingWindow=3,      # speed weighted-moving-average window
                    kickStartGrace=20):     # ticks of grace after (re)play

        self.player = player
        self.log = log if log else print

        self.deadZoneEnter = deadZoneEnter
        self.deadZoneExit = deadZoneExit
        self.seekThreshold = seekThreshold
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

    # Reset servo state + grace period: call on every new play
    def arm(self):
        self.kickStart = self.kickStartGrace
        self.didJump = False
        self.speedHistory = []
        self.inDeadZone = False
        self.lastPos = -1
        self.lastSpeed = 1.0

    # Freewheel: back to speed 1.0, clear servo state (clock lost / master gone)
    def release(self):
        if self.lastSpeed != 1.0:
            self.player.speed(1.0)
            self.lastSpeed = 1.0
        self.speedHistory = []
        self.inDeadZone = False
        self.lastPos = -1
        self.kickStart = 0

    # One servo step against the estimated master clock (s, media timeline).
    # duration (s): enables wrap arithmetic on looping media (0 = unknown).
    # Returns telemetry dict, or None if the tick was dropped.
    def tick(self, clock, duration=0):

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

        speed = 1.0
        fix = 0     # latency corrector (clock source to tracker), kept from nowde
        jumped = False

        # Hard seek: desync beyond servo reach
        if abs(diff) > self.seekThreshold:
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
                    if diff > 3.0:
                        speed = 8.0
                    elif diff > 1.5:
                        speed = round(1 + (diff + fix) * 2.0, 2)
                        speed = min(speed, 6.0)
                    elif diff > 0.8:
                        speed = round(1 + (diff + fix) * 1.5, 2)
                        speed = min(speed, 3.0)
                    elif diff > 0.4:
                        speed = round(1 + (diff + fix) * 1.2, 2)
                        speed = min(speed, 2.0)
                    elif diff > 0.2:
                        speed = round(1 + (diff + fix) * 0.5, 2)
                        speed = min(speed, 1.15)
                    else:
                        speed = round(1 + (diff + fix) * 0.25, 2)
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
                        speed = max(speed, 0.975)
                    else:
                        speed = round(1 + (diff + fix) * 0.15, 2)
                        speed = max(speed, 0.99)

                # Speed smoothing to reduce oscillation
                self.speedHistory.append(speed)
                if len(self.speedHistory) > self.smoothingWindow:
                    self.speedHistory.pop(0)

                # Weighted average favoring recent values (skip in extreme situations)
                if len(self.speedHistory) >= 2 and abs(diff) < 1.0:
                    weights = [i + 1 for i in range(len(self.speedHistory))]
                    smoothed = sum(s * w for s, w in zip(self.speedHistory, weights)) / sum(weights)
                    speed = round(smoothed, 2)
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
