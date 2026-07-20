// TELECO2 — HPlayer2 USB remote (M5Stack CoreS3)
// Plugs into any HPlayer2 player over USB, speaks protocol v1
// (spec: core/interfaces/teleco2.py header). Host side: hplayer.addInterface('teleco2').

#include <M5Unified.h>
#include "state.h"
#include "link.h"
#include "ui.h"

AppState S;

void setup() {
    auto cfg = M5.config();
    M5.begin(cfg);
    linkBegin();
    uiBegin();
}

void loop() {
    M5.update();
    linkLoop();
    uiLoop();
    delay(5);
}
