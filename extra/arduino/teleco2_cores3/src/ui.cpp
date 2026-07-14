#include <M5Unified.h>
#include "state.h"
#include "link.h"
#include "ui.h"

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

static void drawWifiBars(M5Canvas& c, int x, int base) {
    for (int b = 0; b < 4; b++) {
        int h = 3 + b * 3;
        uint16_t col = (S.rssi > b * 25) ? C_CYAN : C_PANEL;
        c.fillRect(x + b * 5, base - h, 4, h, col);
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
        if (S.byed) {
            bar.setTextColor(C_DIM);
            bar.drawString("PLAYER OFF", 6, (BAR_H - 2) / 2);
        } else {
            bar.fillRect(2, 3, 104, BAR_H - 8, C_RED);
            bar.setTextColor(C_BG);
            bar.drawString("NO LINK", 12, (BAR_H - 2) / 2);
        }
        if (S.hostName[0]) {
            bar.setTextColor(C_CYAN);
            bar.drawString(S.hostName, 116, (BAR_H - 2) / 2);
        }
    } else {
        // state glyph + marquee title (white content, colored state)
        drawStateGlyph(bar, 3, (BAR_H - 2) / 2);
        bar.setFont(F_MONO);
        bar.setTextDatum(middle_left);
        bar.setTextColor(S.med[0] ? C_PAPER : C_DIM);
        const char* title = S.med[0] ? S.med : "-- NO MEDIA --";
        const int winX = 18, winW = 150;
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

        // labeled readouts: SYNC / RSSI / VOL
        char v[8];
        bar.setTextDatum(bottom_center);

        microLabel(bar, "SYNC", 192, 2);
        bar.setFont(F_MONO);
        bar.setTextColor(S.peersTotal > 1 ? C_CYAN : C_DIM);
        snprintf(v, sizeof(v), "%d", S.peersTotal);
        bar.setTextDatum(bottom_center);
        bar.drawString(v, 192, BAR_H - 3);

        microLabel(bar, "RSSI", 232, 2);
        drawWifiBars(bar, 222, BAR_H - 5);

        microLabel(bar, "VOL", 280, 2);
        bar.setFont(F_MONO);
        bar.setTextDatum(bottom_center);
        if (S.mute) {
            bar.setTextColor(C_RED);
            bar.drawString("MUTE", 280, BAR_H - 3);
        } else {
            bar.setTextColor(C_AMBER);
            snprintf(v, sizeof(v), "%d", S.vol);
            bar.drawString(v, 280, BAR_H - 3);
        }
    }

    if (S.locked) {     // inverted LOCK tag, far right
        bar.fillRect(304, 3, 16, BAR_H - 8, C_AMBER);
        bar.setFont(F_MICRO);
        bar.setTextColor(C_BG);
        bar.setTextDatum(middle_center);
        bar.drawString("L", 312, (BAR_H - 2) / 2);
    }

    bar.pushSprite(0, 0);
}

//
// page area
//

static void drawWaiting(M5Canvas& c) {
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
    uint32_t lastTapMs = 0;
    int      lastTapX = 0, lastTapY = 0;
} T;

static void setLock(bool on) {
    S.locked = on;
    M5.Display.setBrightness(on ? BRIGHT_LOCKED : BRIGHT_NORMAL);
    S.dBar = S.dPage = true;
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
    }
}

static void handleTouch() {
    auto t = M5.Touch.getDetail();

    if (t.wasPressed()) {
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
            uint32_t now = millis();
            bool dbl = (now - T.lastTapMs < 400)
                    && abs(T.startX - T.lastTapX) < 40
                    && abs(T.startY - T.lastTapY) < 40;
            T.lastTapMs = now; T.lastTapX = T.startX; T.lastTapY = T.startY;

            if (S.locked) {                                 // locked: only unlock double-tap
                if (dbl) setLock(false);
                return;
            }
            if (dbl && T.startY < BAR_H) {                  // lock: double-tap the status bar
                setLock(true);
                return;
            }
            tap(T.startX, T.startY);
        }
    }
}

//
// public
//

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
