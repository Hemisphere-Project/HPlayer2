#include <M5Unified.h>
#include "state.h"
#include "link.h"
#include "power.h"
#include "ui.h"

#define BAT_READ_MS     2000
#define BAT_REPORT_MS   30000
#define VBUS_MV         4000    // USB power present above this

static uint32_t lastTouch = 0;
static uint32_t lastRead = 0;
static uint32_t lastReport = 0;

static void readBattery() {
    int  b = M5.Power.getBatteryLevel();
    bool c = M5.Power.isCharging() == m5::Power_Class::is_charging;
    bool v = M5.Power.getVBUSVoltage() > VBUS_MV;
    if (b != S.bat || c != S.chg || v != S.vbus) S.dBar = true;
    S.bat = b;
    S.chg = c;
    S.vbus = v;
}

static void undim() {
    if (!S.dimmed) return;
    S.dimmed = false;
    M5.Display.setBrightness(BRIGHT_NORMAL);
}

void powerBegin() {
    setCpuFrequencyMhz(160);            // enough for the UI and WiFi, ~20% less than 240
    M5.Power.setExtOutput(false);       // the 5 V boost feeds nothing on a remote
    readBattery();
    lastTouch = millis();
}

bool powerWake() {
    lastTouch = millis();
    if (S.offIn >= 0) S.noWifiSince = millis();    // touched during the countdown: stay on
    if (S.dimmed) {
        undim();
        S.dBar = S.dPage = true;
        return true;                    // the waking touch only wakes
    }
    return false;
}

void powerActivity() {
    lastTouch = millis();
    undim();
}

void powerLoop() {
    uint32_t now = millis();

    if (now - lastRead > BAT_READ_MS) {
        lastRead = now;
        readBattery();
    }
    if (S.linked && S.bat >= 0 && now - lastReport > BAT_REPORT_MS) {
        lastReport = now;
        char l[24];
        snprintf(l, sizeof(l), "bat %d %d", S.bat, S.chg ? 1 : 0);
        sendCmd(l);                     // the player logs it (a 10-point move or a charge change)
    }

    bool battery = S.mode == MODE_NET;

    // 10 min without WiFi, on battery: say it, then power off (a forgotten remote out of range)
    int off = -1;
    if (battery && !S.vbus && S.net == NET_NOWIFI && S.noWifiSince) {
        uint32_t gone = (now - S.noWifiSince) / 1000;
        if (gone >= OFF_AFTER_S) {
            uiPowerOff();               // the screen says why, bright, for 3 s
            delay(3000);
            M5.Power.powerOff();
        } else if (gone + OFF_WARN_S >= OFF_AFTER_S) {
            off = OFF_AFTER_S - gone;
        }
    }
    if (off != S.offIn) {
        S.offIn = off;
        S.dPage = true;
    }

    if (battery && off < 0) {           // (a countdown nobody can read is no warning: bright)
        if (!S.dimmed && now - lastTouch > DIM_MS) {
            S.dimmed = true;
            M5.Display.setBrightness(BRIGHT_DIM);
#if LOCK_ON_DIM
            if (!S.locked) { S.locked = true; S.dBar = S.dPage = true; }
#endif
        }
    } else {
        undim();
    }
    if (battery && !S.locked && now - lastTouch > LOCK_AFTER_IDLE_MS) {
        S.locked = true;
        S.dBar = S.dPage = true;
    }
}
