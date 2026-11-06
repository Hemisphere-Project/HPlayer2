#include <M5Unified.h>
#include "state.h"
#include "link.h"
#include "ui.h"
#include "net.h"
#include "power.h"

static M5Canvas bar(&M5.Display);
static M5Canvas page(&M5.Display);
static M5Canvas tabs(&M5.Display);

//
// status bar — tape-deck display strip: marquee title + labeled readouts
//

static bool marqueeActive = false;

static void microLabel(M5Canvas& c, const char* txt, int x, int y) {
    c.setFont(F_MICRO);
    c.setTextDatum(top_center);
    c.setTextColor(C_DIM);
    c.drawString(txt, x, y);
}

static void drawWifiBars(M5Canvas& c, int x, int base, int rssi) {
    for (int b = 0; b < 4; b++) {
        int h = 3 + b * 3;
        uint16_t col = (rssi > b * 25) ? C_CYAN : C_PANEL;
        c.fillRect(x + b * 5, base - h, 4, h, col);
    }
}

// battery block (centre cx): "BAT" (+ a bolt while charging) over "87%", amber <= 15, red <= 5
static void drawBattery(M5Canvas& c, int cx) {
    uint16_t col = S.bat < 0 ? C_DIM : S.bat <= 5 ? C_RED : S.bat <= 15 ? C_AMBER : S.chg ? C_GREEN : C_PAPER;
    microLabel(c, "BAT", cx - 4, 2);
    if (S.chg) {
        int x = cx + 8, y = 1;
        c.fillTriangle(x + 4, y, x, y + 5, x + 3, y + 5, C_GREEN);
        c.fillTriangle(x + 2, y + 4, x + 6, y + 4, x + 1, y + 10, C_GREEN);
    }
    char v[6];
    if (S.bat < 0) strcpy(v, "--");
    else snprintf(v, sizeof(v), "%d%%", S.bat);
    c.setFont(F_MONO);
    c.setTextColor(col);
    c.setTextDatum(bottom_center);
    c.drawString(v, cx, BAR_H - 3);
}

// link block (x0..x0+56): the player's name over the transport glyph (USB / WiFi arcs) + bars
static void drawLinkBlock(M5Canvas& c, int x0) {
    const char* nm = S.linked && S.hostName[0] ? S.hostName : (S.mode == MODE_NET ? netPlayer() : S.hostName);
    char n9[10];
    strlcpy(n9, nm, sizeof(n9));
    c.setFont(F_MICRO);
    c.setTextDatum(top_center);
    c.setTextColor(S.linked ? C_CYAN : C_DIM);
    c.drawString(n9[0] ? n9 : (S.mode == MODE_NET ? "WIFI" : "USB"), x0 + 28, 2);
    int base = BAR_H - 5;
    if (S.mode == MODE_NET) {
        uint16_t col = S.net >= NET_SEARCH ? C_CYAN : C_RED;
        for (int r = 3; r <= 9; r += 3) c.drawArc(x0 + 8, base, r, r - 1, 225, 315, col);
        c.fillCircle(x0 + 8, base - 1, 1, col);
        drawWifiBars(c, x0 + 20, base, S.wifiRssi);
    } else {
        c.setTextDatum(bottom_left);
        c.setTextColor(C_CYAN);
        c.drawString("USB", x0, base + 1);
        drawWifiBars(c, x0 + 20, base, S.rssi);     // the player's WiFi, as fw 5 showed it
    }
}

static void drawStateGlyph(M5Canvas& c, int x, int cy) {   // play/pause/stop, colored by state
    if (S.pl == 1)      c.fillTriangle(x, cy - 6, x, cy + 6, x + 10, cy, C_GREEN);
    else if (S.pl == 2) { c.fillRect(x, cy - 6, 4, 12, C_AMBER); c.fillRect(x + 6, cy - 6, 4, 12, C_AMBER); }
    else                c.fillRect(x, cy - 5, 10, 10, C_RED);
}

static void drawBar() {
    bar.fillSprite(C_BG);
    bar.drawFastHLine(0, BAR_H - 2, SCREEN_W, C_AMBER);    // deck rule

    if (S.byed || !S.linked) {
        bar.setFont(F_MONO);
        bar.setTextDatum(middle_left);
        if (S.mode == MODE_NET) {               // fw 6, on WiFi: NO WIFI -> SEARCHING -> LINK
            bool red = S.net <= NET_NOWIFI;
            bar.fillRect(2, 3, 112, BAR_H - 8, red ? C_RED : C_AMBER);
            bar.setTextColor(C_BG);
            bar.drawString(red ? "NO WIFI" : S.net == NET_SEARCH ? "SEARCHING" : "LINKING", 8, (BAR_H - 2) / 2);
        } else if (S.byed) {
            bar.setTextColor(C_DIM);
            bar.drawString("PLAYER OFF", 6, (BAR_H - 2) / 2);
        } else {
            bar.fillRect(2, 3, 104, BAR_H - 8, C_RED);
            bar.setTextColor(C_BG);
            bar.drawString("NO LINK", 12, (BAR_H - 2) / 2);
        }
        drawBattery(bar, 173);
        drawLinkBlock(bar, 200);
    } else {
        // state glyph + marquee title (white content, colored state)
        drawStateGlyph(bar, 3, (BAR_H - 2) / 2);
        bar.setFont(F_MONO);
        bar.setTextDatum(middle_left);
        bar.setTextColor(S.med[0] ? C_PAPER : C_DIM);
        const char* title = S.med[0] ? S.med : "-- NO MEDIA --";
        const int winX = 18, winW = S.mute ? 84 : 128;
        int tw = bar.textWidth(title);
        int off = 0;
        marqueeActive = tw > winW;
        if (marqueeActive) {
            const int gap = 40;
            int span = tw + gap;
            uint32_t period = 1500 + (uint32_t)span * 33;
            uint32_t ph = millis() % period;
            if (ph > 1500) off = (ph - 1500) / 33 % span;
            bar.setClipRect(winX, 0, winW, BAR_H - 2);
            bar.drawString(title, winX + 2 - off, (BAR_H - 2) / 2);
            bar.drawString(title, winX + 2 - off + span, (BAR_H - 2) / 2);
            bar.clearClipRect();
        } else {
            bar.drawString(title, winX + 2, (BAR_H - 2) / 2);
        }

        // mute alert (volume itself lives on the PLAY page)
        if (S.mute) {
            bar.fillRect(106, 4, 40, BAR_H - 10, C_RED);
            bar.setFont(F_MICRO);
            bar.setTextDatum(middle_center);
            bar.setTextColor(C_BG);
            bar.drawString("MUTE", 126, (BAR_H - 2) / 2);
        }

        // readouts: battery / player + transport + signal / SYNC
        drawBattery(bar, 173);
        drawLinkBlock(bar, 200);

        char v[8];
        microLabel(bar, "SYNC", 279, 2);
        bar.setFont(F_MONO);
        bar.setTextColor(S.peersTotal > 1 ? C_CYAN : C_DIM);
        snprintf(v, sizeof(v), "%d", S.peersTotal);
        bar.setTextDatum(bottom_center);
        bar.drawString(v, 279, BAR_H - 3);
    }

    if (S.locked) {     // padlock, far right
        bar.drawRoundRect(306, 3, 11, 11, 3, C_AMBER);      // shackle
        bar.fillRoundRect(302, 10, 19, 12, 2, C_AMBER);     // body
        bar.fillRect(310, 14, 3, 5, C_BG);                  // keyhole
    }

    bar.pushSprite(0, 0);
}

//
// page area
//

static void drawWaitingNet(M5Canvas& c) {
    const char* big = S.net <= NET_NOWIFI ? "NO WIFI" : S.net == NET_SEARCH ? "SEARCHING" : "LINKING";
    char small[48];
    if (S.net <= NET_NOWIFI) snprintf(small, sizeof(small), "joining %s ...", netSsid());
    else if (S.net == NET_SEARCH) snprintf(small, sizeof(small), "players heard: %d", S.heard);
    else snprintf(small, sizeof(small), "%s", netPlayer());
    c.setFont(F_MONO_BIG);
    c.setTextDatum(middle_center);
    c.setTextColor(S.net <= NET_NOWIFI ? C_RED : C_AMBER);
    c.drawString(big, SCREEN_W / 2, PAGE_H / 2 - 24);
    c.setFont(F_MONO);
    c.setTextColor(S.net == NET_LINK ? C_CYAN : C_DIM);
    c.drawString(small, SCREEN_W / 2, PAGE_H / 2 + 8);
    if (S.offIn >= 0) {
        snprintf(small, sizeof(small), "power off in %d s - touch to stay on", S.offIn);
        c.setFont(F_MICRO);
        c.setTextColor(C_AMBER);
        c.drawString(small, SCREEN_W / 2, PAGE_H / 2 + 34);
    } else if (S.pinned[0]) {
        snprintf(small, sizeof(small), "pinned: %s", S.pinned);
        c.setTextColor(C_CYAN);
        c.drawString(small, SCREEN_W / 2, PAGE_H / 2 + 32);
    }
    c.drawRect(24, 8, SCREEN_W - 48, PAGE_H - 16, C_LINE);
}

static void drawWaiting(M5Canvas& c) {
    if (S.mode == MODE_NET) return drawWaitingNet(c);
    c.setFont(F_MONO_BIG);
    c.setTextDatum(middle_center);
    c.setTextColor(C_AMBER);
    c.drawString(S.byed ? "PLAYER OFF" : "NO CARRIER", SCREEN_W / 2, PAGE_H / 2 - 24);
    c.setFont(F_MONO);
    c.setTextColor(C_DIM);
    c.drawString(S.byed ? "player was shut down" : "waiting for HPlayer2...", SCREEN_W / 2, PAGE_H / 2 + 8);
    if (S.hostName[0]) {
        c.setTextColor(C_CYAN);
        c.drawString(S.hostName, SCREEN_W / 2, PAGE_H / 2 + 32);
    }
    c.drawRect(24, 8, SCREEN_W - 48, PAGE_H - 16, C_LINE);
}

static void drawPage() {
    page.fillSprite(C_BG);
    if (!S.linked) drawWaiting(page);
    else if (S.page == 0) drawTransport(page);
    else if (S.page == 1) drawMedia(page);
    else drawPeers(page);

    if (S.toastKind != TOAST_NONE) {    // lock feedback overlay
        uint16_t col = (S.toastKind == TOAST_UNLOCKED) ? C_GREEN : C_AMBER;
        int by = PAGE_H / 2 - 34;
        page.fillRoundRect(36, by, SCREEN_W - 72, 68, 6, C_PANEL);
        page.drawRoundRect(36, by, SCREEN_W - 72, 68, 6, col);
        page.setTextDatum(middle_center);
        page.setFont(F_MONO_BIG);
        page.setTextColor(col);
        page.drawString(S.toastKind == TOAST_UNLOCKED ? "UNLOCKED" : "LOCKED",
                        SCREEN_W / 2, by + (S.toastKind == TOAST_UNLOCKED ? 34 : 24));
        if (S.toastKind != TOAST_UNLOCKED) {
            page.setFont(F_MICRO);
            page.setTextColor(C_PAPER);
            page.drawString("tap PLAY 5x fast to unlock", SCREEN_W / 2, by + 48);
        }
    }

    page.pushSprite(0, PAGE_Y);
}

//
// tab bar — deck mode keys: [PLAY] [MEDIA] [PEERS]
//

static const char* TAB_NAMES[3] = {"PLAY", "MEDIA", "PEERS"};

static void drawTabs() {
    tabs.fillSprite(C_BG);
    tabs.drawFastHLine(0, 0, SCREEN_W, C_LINE);
    tabs.setFont(F_MONO);
    tabs.setTextDatum(middle_center);
    for (int i = 0; i < 3; i++) {
        int x = i * (SCREEN_W / 3);
        if (i == S.page) {
            tabs.fillRect(x + 4, 4, SCREEN_W / 3 - 8, TAB_H - 8, C_AMBER);
            tabs.setTextColor(C_BG);
        } else {
            tabs.drawRect(x + 4, 4, SCREEN_W / 3 - 8, TAB_H - 8, C_DIM);
            tabs.setTextColor(C_DIM);
        }
        tabs.drawString(TAB_NAMES[i], x + SCREEN_W / 6, TAB_H / 2 + 1);
    }
    tabs.pushSprite(0, TAB_Y);
}

//
// touch: tap / double-tap / vertical drag, hand-rolled on M5.Touch primitives
//

static struct {
    bool     pressed = false;
    bool     dragged = false;
    int      startX = 0, startY = 0, lastY = 0;
    uint32_t startMs = 0;
} T;

static struct {         // fast-tap sequence on the [PLAY] tab toggles the lock
    uint8_t  count = 0;
    uint32_t lastMs = 0;
} K;

static void setLock(bool on) {
    S.locked = on;
    S.dBar = S.dPage = true;
}

static void toast(uint8_t kind) {
    S.toastKind = kind;
    S.toastUntil = millis() + 1500;
    S.dPage = true;
}

static bool lockTap(int x, int y) {     // counts fast taps on [PLAY]; true when the lock toggled
    uint32_t now = millis();
    if (y >= TAB_Y && x < SCREEN_W / 3 && now - K.lastMs < LOCK_TAP_MS) {
        K.lastMs = now;
        if (++K.count >= LOCK_TAP_N) {
            K.count = 0;
            setLock(!S.locked);
            toast(S.locked ? TOAST_LOCKED : TOAST_UNLOCKED);
            return true;
        }
        return false;
    }
    K.count = (y >= TAB_Y && x < SCREEN_W / 3) ? 1 : 0;
    K.lastMs = now;
    return false;
}

static void tap(int x, int y) {
    if (y >= TAB_Y) {
        uint8_t p = x / (SCREEN_W / 3);
        if (p != S.page && p < 3) {
            S.page = p;
            S.dPage = true;
            drawTabs();
        }
    } else if (y >= PAGE_Y && S.linked) {
        if (S.page == 0) tapTransport(x, y - PAGE_Y);
        else if (S.page == 1) tapMedia(x, y - PAGE_Y);
        else tapPeers(x, y - PAGE_Y);
    }
}

static bool swallowing = false;    // the touch that woke a dimmed screen, until released

static void handleTouch() {
    auto t = M5.Touch.getDetail();

    if (swallowing) {
        if (!t.isPressed()) swallowing = false;
        return;
    }
    if (S.dimmed && (t.wasPressed() || t.isPressed())) {
        powerWake();                    // wakes only: never a button
        swallowing = true;
        T.pressed = false;
        return;
    }

    if (t.wasPressed()) {
        powerWake();                    // (not dimmed: just the idle clock)
        T.pressed = true;
        T.dragged = false;
        T.startX = t.x; T.startY = t.y; T.lastY = t.y;
        T.startMs = millis();
    }

    if (T.pressed && t.isPressed()) {
        if (abs(t.y - T.startY) > 12) T.dragged = true;
        if (T.dragged && !S.locked && S.linked && S.page == 1 && T.startY > PAGE_Y && T.startY < TAB_Y)
            mediaScroll(t.y - T.lastY);
        T.lastY = t.y;
    }

    if (T.pressed && t.wasReleased()) {
        T.pressed = false;
        if (!T.dragged && millis() - T.startMs < 500) {     // a tap
            if (lockTap(T.startX, T.startY))                // fast-tap [PLAY] toggles the lock
                return;
            if (S.locked && T.startY < TAB_Y) {             // locked: only page change allowed
                toast(TOAST_DENIED);
                return;
            }
            tap(T.startX, T.startY);
        }
    }
}

//
// public
//

void uiPowerOff() {
    M5.Display.setBrightness(BRIGHT_NORMAL);
    M5.Display.fillScreen(C_BG);
    M5.Display.setTextDatum(middle_center);
    M5.Display.setFont(F_MONO_BIG);
    M5.Display.setTextColor(C_AMBER);
    M5.Display.drawString("NO WIFI FOR 10 MIN", SCREEN_W / 2, SCREEN_H / 2 - 30);
    M5.Display.setTextColor(C_RED);
    M5.Display.drawString("POWERING OFF", SCREEN_W / 2, SCREEN_H / 2 + 4);
    M5.Display.setFont(F_MONO);
    M5.Display.setTextColor(C_DIM);
    M5.Display.drawString("power button to restart", SCREEN_W / 2, SCREEN_H / 2 + 40);
}

void uiBegin() {
    M5.Display.setBrightness(BRIGHT_NORMAL);
    M5.Display.fillScreen(C_BG);
    bar.createSprite(SCREEN_W, BAR_H);
    page.createSprite(SCREEN_W, PAGE_H);
    tabs.createSprite(SCREEN_W, TAB_H);
    drawBar();
    drawPage();
    drawTabs();
}

void uiLoop() {
    handleTouch();

    uint32_t now = millis();
    static uint32_t lastBarMs = 0;

    if (S.toastKind != TOAST_NONE && (int32_t)(now - S.toastUntil) >= 0) {
        S.toastKind = TOAST_NONE;
        S.dPage = true;
    }

    // bar: on change, marquee tick, or slow heartbeat
    if (S.dBar || (marqueeActive && now - lastBarMs > 33) || now - lastBarMs > 500) {
        S.dBar = false;
        lastBarMs = now;
        drawBar();
    }

    if (S.dPage) {
        S.dPage = false;
        drawPage();
    }
}
