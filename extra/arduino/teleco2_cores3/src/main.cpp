// TELECO2 — HPlayer2 remote (M5Stack CoreS3)
// Plugged into a player: protocol v1 over the USB (fw <= 5 behaviour). On its battery (fw 6,
// hplayer2#t-090): the same protocol over WiFi/TCP to a player found by a UDP probe.
// Spec: core/interfaces/teleco2.py header. Host side: hplayer.addInterface('teleco2', ..., netport=3740).

#include <M5Unified.h>
#include "state.h"
#include "link.h"
#include "net.h"
#include "power.h"
#include "ui.h"

AppState S;

void setup() {
    auto cfg = M5.config();
    cfg.internal_imu = false;           // a remote: no IMU, no speaker, no mic (battery)
    cfg.internal_spk = false;
    cfg.internal_mic = false;
    cfg.output_power = false;           // no 5 V on the bus
    M5.begin(cfg);
    // FT6336 touch: never drop to monitor mode, or the first tap after idle (the wake tap) is lost
    // (knowledge cores3-touch-monitor-mode-drops-taps, hplayer0 ce34c9b)
    M5.In_I2C.writeRegister8(0x38, 0x86, 0x00, 400000);
    powerBegin();
    netBegin();
    linkBegin();
    uiBegin();
}

void loop() {
    M5.update();
    powerLoop();
    linkLoop();
    uiLoop();
    delay(5);
}
