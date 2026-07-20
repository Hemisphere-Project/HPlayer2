#include <M5Unified.h>
#include "state.h"
#include "link.h"
#include "ui.h"

//
// TRANSPORT page — outlined deck keys + 7-seg volume + segmented progress
//

#define BTN_W       112
#define BTN_H       70
#define BTN_X0      6
#define BTN_X1      (BTN_X0 + BTN_W + 6)
#define BTN_Y0      6
#define BTN_Y1      (BTN_Y0 + BTN_H + 6)
#define VOL_X       (BTN_X1 + BTN_W + 6)
#define VOL_W       (SCREEN_W - VOL_X - 6)
#define VOL_BTN_H   46
#define PROG_Y      (BTN_Y1 + BTN_H + 8)

static void deckKey(M5Canvas& c, int x, int y, int w, int h, const char* label) {
    c.fillRoundRect(x, y, w, h, 4, C_PANEL);
    c.drawRoundRect(x, y, w, h, 4, C_AMBER);
    if (label) {
        c.setFont(F_MICRO);
        c.setTextDatum(bottom_center);
        c.setTextColor(C_DIM);
        c.drawString(label, x + w / 2, y + h - 4);
    }
}

static void iconPrev(M5Canvas& c, int cx, int cy) {
    c.fillRect(cx - 22, cy - 12, 5, 24, C_PAPER);
    c.fillTriangle(cx - 14, cy, cx + 2, cy - 12, cx + 2, cy + 12, C_PAPER);
    c.fillTriangle(cx + 4, cy, cx + 20, cy - 12, cx + 20, cy + 12, C_PAPER);
}

static void iconNext(M5Canvas& c, int cx, int cy) {
    c.fillTriangle(cx - 20, cy - 12, cx - 20, cy + 12, cx - 4, cy, C_PAPER);
    c.fillTriangle(cx - 2, cy - 12, cx - 2, cy + 12, cx + 14, cy, C_PAPER);
    c.fillRect(cx + 17, cy - 12, 5, 24, C_PAPER);
}

static void iconPlayPause(M5Canvas& c, int cx, int cy) {
    if (S.pl == 1) {    // playing -> key acts as PAUSE
        c.fillRect(cx - 11, cy - 13, 8, 26, C_AMBER);
        c.fillRect(cx + 3, cy - 13, 8, 26, C_AMBER);
    } else {            // stopped / paused -> key acts as PLAY
        c.fillTriangle(cx - 9, cy - 13, cx - 9, cy + 13, cx + 13, cy, C_GREEN);
    }
}

static void iconStop(M5Canvas& c, int cx, int cy) {
    c.fillRect(cx - 12, cy - 12, 24, 24, C_RED);
}

void drawTransport(M5Canvas& c) {
    deckKey(c, BTN_X0, BTN_Y0, BTN_W, BTN_H, "PREV");
    iconPrev(c, BTN_X0 + BTN_W / 2, BTN_Y0 + BTN_H / 2 - 4);
    deckKey(c, BTN_X1, BTN_Y0, BTN_W, BTN_H, S.pl == 1 ? "PAUSE" : "PLAY");
    iconPlayPause(c, BTN_X1 + BTN_W / 2, BTN_Y0 + BTN_H / 2 - 4);
    deckKey(c, BTN_X0, BTN_Y1, BTN_W, BTN_H, "STOP");
    iconStop(c, BTN_X0 + BTN_W / 2, BTN_Y1 + BTN_H / 2 - 4);
    deckKey(c, BTN_X1, BTN_Y1, BTN_W, BTN_H, "NEXT");
    iconNext(c, BTN_X1 + BTN_W / 2, BTN_Y1 + BTN_H / 2 - 4);

    // volume column: [+] / 7-seg readout / [-]
    deckKey(c, VOL_X, BTN_Y0, VOL_W, VOL_BTN_H, NULL);
    deckKey(c, VOL_X, PROG_Y - VOL_BTN_H - 8, VOL_W, VOL_BTN_H, NULL);
    c.setFont(F_MONO_BIG);
    c.setTextDatum(middle_center);
    c.setTextColor(C_AMBER);
    c.drawString("+", VOL_X + VOL_W / 2, BTN_Y0 + VOL_BTN_H / 2);
    c.drawString("-", VOL_X + VOL_W / 2, PROG_Y - 8 - VOL_BTN_H / 2);

    char v[8];
    snprintf(v, sizeof(v), "%d", S.vol);
    c.setFont(F_7SEG);
    c.setTextSize(0.55f);
    c.setTextDatum(middle_center);
    c.setTextColor(S.mute ? C_RED : C_AMBER);
    c.drawString(S.mute ? "0" : v, VOL_X + VOL_W / 2, (BTN_Y0 + VOL_BTN_H + PROG_Y - VOL_BTN_H - 8) / 2);
    c.setTextSize(1.0f);
    c.setFont(F_MICRO);
    c.setTextColor(C_DIM);
    c.drawString(S.mute ? "MUTED" : "VOL", VOL_X + VOL_W / 2, (BTN_Y0 + VOL_BTN_H + PROG_Y - VOL_BTN_H - 8) / 2 + 22);

    // progress strip: track counter + segment meter + time
    c.setFont(F_MONO);
    c.setTextDatum(middle_left);
    c.setTextColor(C_PAPER);
    char nfo[16];
    if (S.idx >= 0) snprintf(nfo, sizeof(nfo), "%02d/%02d", S.idx + 1, S.count);
    else            snprintf(nfo, sizeof(nfo), "--/%02d", S.count);
    c.drawString(nfo, BTN_X0, PROG_Y + 9);

    const int segN = 20, segW = 7, segH = 14, segX = 78;
    int fill = (S.dur > 0) ? (int)((int32_t)segN * S.pos / S.dur) : 0;
    if (fill > segN) fill = segN;
    for (int i = 0; i < segN; i++) {
        uint16_t col = (i < fill) ? (S.pl == 2 ? C_AMBER : C_GREEN) : C_PANEL;
        c.fillRect(segX + i * (segW + 2), PROG_Y + 2, segW, segH, col);
    }

    char tim[8];
    snprintf(tim, sizeof(tim), "%d:%02d", S.pos / 60, S.pos % 60);
    c.setTextDatum(middle_right);
    c.setTextColor(C_DIM);
    c.drawString(tim, SCREEN_W - 8, PROG_Y + 9);
    c.setTextDatum(middle_left);
}

void tapTransport(int x, int y) {
    if (x >= VOL_X && x < VOL_X + VOL_W) {
        if (y >= BTN_Y0 && y < BTN_Y0 + VOL_BTN_H) {
            S.vol = min(100, S.vol + 1);
            S.volSuppressUntil = millis() + 500;    // optimistic, ignore echo
            sendCmd("volup");
        } else if (y >= PROG_Y - VOL_BTN_H - 8 && y < PROG_Y - 8) {
            S.vol = max(0, S.vol - 1);
            S.volSuppressUntil = millis() + 500;
            sendCmd("voldown");
        } else {
            return;
        }
        S.dBar = S.dPage = true;
        return;
    }
    int col = (x >= BTN_X1) ? 1 : 0;
    if (x < BTN_X0 || x >= BTN_X1 + BTN_W) return;
    if (y >= BTN_Y0 && y < BTN_Y0 + BTN_H) sendCmd(col ? "playpause" : "prev");
    else if (y >= BTN_Y1 && y < BTN_Y1 + BTN_H) sendCmd(col ? "next" : "stop");
}

//
// MEDIA page — mono list, inverted current row, tap to play
//

static int scrollAccum = 0;

static int mediaRows() {
    int rows = S.listLoaded;
    if (S.listTotal > S.listLoaded) rows++;     // "+N MORE" footer row
    return rows;
}

void drawMedia(M5Canvas& c) {
    c.setFont(F_MONO);
    c.setTextDatum(middle_left);

    if (!S.listLoaded) {
        c.setTextColor(C_DIM);
        c.setTextDatum(middle_center);
        c.drawString("NO MEDIA", SCREEN_W / 2, PAGE_H / 2);
        return;
    }

    int visible = PAGE_H / ROW_H;
    int rows = mediaRows();
    if (S.listScroll > rows - visible) S.listScroll = max(0, rows - visible);

    char txt[64];
    for (int r = 0; r < visible; r++) {
        int i = S.listScroll + r;
        if (i >= rows) break;
        int y = r * ROW_H;
        if (i >= (int)S.listLoaded) {           // footer
            snprintf(txt, sizeof(txt), "... +%d MORE", S.listTotal - S.listLoaded);
            c.setTextColor(C_DIM);
            c.drawString(txt, 10, y + ROW_H / 2);
            break;
        }
        bool cur = (i == S.idx);
        if (cur) {                              // inverted current row
            uint16_t rowCol = (S.pl == 1) ? C_GREEN : C_AMBER;
            c.fillRect(0, y + 1, SCREEN_W - 8, ROW_H - 2, rowCol);
            c.setTextColor(C_BG);
            snprintf(txt, sizeof(txt), "%02d %s", i + 1, S.list[i]);
            c.drawString(txt, 8, y + ROW_H / 2);
        } else {                                // dim index, white name
            snprintf(txt, sizeof(txt), "%02d", i + 1);
            c.setTextColor(C_DIM);
            c.drawString(txt, 8, y + ROW_H / 2);
            c.setTextColor(C_PAPER);
            c.drawString(S.list[i], 42, y + ROW_H / 2);
        }
    }

    // scrollbar
    if (rows > visible) {
        int sbH = max(12, PAGE_H * visible / rows);
        int sbY = (PAGE_H - sbH) * S.listScroll / (rows - visible);
        c.fillRect(SCREEN_W - 5, sbY, 4, sbH, C_DIM);
    }
}

void mediaScroll(int dyPx) {
    scrollAccum += dyPx;
    int rows = scrollAccum / ROW_H;
    if (rows != 0) {
        scrollAccum -= rows * ROW_H;
        int visible = PAGE_H / ROW_H;
        S.listScroll = constrain(S.listScroll - rows, 0, max(0, mediaRows() - visible));
        S.dPage = true;
    }
}

void tapMedia(int x, int y) {
    int i = S.listScroll + (y / ROW_H);
    if (i >= 0 && i < (int)S.listLoaded)
        sendCmdi("playindex", i);
}

//
// PEERS page — LED square + mono name + link state
//

void drawPeers(M5Canvas& c) {
    c.setFont(F_MONO);
    c.setTextDatum(middle_left);

    if (!S.peersN) {
        c.setTextColor(C_DIM);
        c.setTextDatum(middle_center);
        c.drawString("NO PEERS", SCREEN_W / 2, PAGE_H / 2);
        return;
    }

    static const uint16_t LK_COL[4] = {C_RED, C_DIM, C_AMBER, C_GREEN};
    static const char* LK_TXT[4] = {"GONE", "SILENT", "EVASIVE", "OK"};

    char txt[40];
    int visible = PAGE_H / ROW_H;
    for (int r = 0; r < visible && r < S.peersN; r++) {
        int y = r * ROW_H;
        const Peer& p = S.peers[r];
        c.fillRect(8, y + ROW_H / 2 - 5, 10, 10, LK_COL[p.lk & 3]);
        c.drawRect(7, y + ROW_H / 2 - 6, 12, 12, C_LINE);
        snprintf(txt, sizeof(txt), "%s%s", p.nm, p.me ? " *" : "");
        c.setTextColor(p.me ? C_CYAN : C_PAPER);
        c.drawString(txt, 28, y + ROW_H / 2);
        c.setTextColor(LK_COL[p.lk & 3]);
        c.setTextDatum(middle_right);
        c.drawString(LK_TXT[p.lk & 3], SCREEN_W - 10, y + ROW_H / 2);
        c.setTextDatum(middle_left);
    }
    if (S.peersN > visible) {
        snprintf(txt, sizeof(txt), "+%d", S.peersN - visible);
        c.setTextColor(C_DIM);
        c.setTextDatum(middle_right);
        c.drawString(txt, SCREEN_W - 10, PAGE_H - 8);
        c.setTextDatum(middle_left);
    }
}
