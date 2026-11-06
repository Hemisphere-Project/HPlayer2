#include <Arduino.h>
#include <ArduinoJson.h>
#include "state.h"
#include "link.h"
#include "net.h"
#include "power.h"
#include "version.h"

#define RX_BUF          640
#define STALE_MS        8000    // USB: host silent this long -> unlinked (fw 5)
#define HELLO_MS        3000
#define USB_LISTEN_MS   4000    // boot on VBUS: listen to the USB this long before going wireless

#define STR_(x)     #x
#define STR(x)      STR_(x)

static char     buf[RX_BUF];
static size_t   bufLen = 0;
static bool     overflow = false;
static uint32_t lastHello = 0;
static uint32_t lastResync = 0;
static uint32_t lastSerialRx = 0;
static uint32_t bootAt = 0;
static char     helloLine[48];

const char* linkHello() { return helloLine; }

static void serialLine(const char* line) {
    Serial.print(line);
    Serial.print('\n');
}

static void sendLine(const char* line) {
    if (S.mode == MODE_NET) netSend(line);      // dropped unless a session is alive
    else serialLine(line);
}

void sendCmd(const char* cmd) {
    sendLine(cmd);
}

void sendCmdi(const char* cmd, int arg) {
    char l[48];
    snprintf(l, sizeof(l), "%s %d", cmd, arg);
    sendLine(l);
}

static void setMode(uint8_t m) {
    if (S.mode == m) return;
    S.mode = m;
    S.linked = false;
    S.byed = false;
    netEnable(m == MODE_NET);                   // USB mode: WiFi OFF, one transport at a time
    powerActivity();                            // a mode change is worth a bright screen
    S.dBar = S.dPage = true;
}

static void copyStr(char* dst, size_t cap, JsonVariantConst v) {
    strlcpy(dst, v | "", cap);
}

void linkParse(const char* line, bool fromSerial) {
    JsonDocument doc;
    if (deserializeJson(doc, line) != DeserializationError::Ok) return;  // boot spew, noise..
    const char* t = doc["t"] | "";
    if (!*t) return;

    if (fromSerial) {
        lastSerialRx = millis();
        if (S.mode != MODE_USB) {
            if (!S.vbus) return;                // no USB power: not a player on our port
            setMode(MODE_USB);                  // a player talks on our USB: it wins, WiFi goes off
        }
    } else if (S.mode != MODE_NET) {
        return;                                 // a late TCP line after the switch to USB
    }

    S.lastRx = millis();
    if (!S.linked) {
        S.linked = true;
        S.byed = false;
    }

    if (!strcmp(t, "st")) {
        S.pl    = doc["pl"]  | 0;
        S.idx   = doc["i"]   | -1;
        S.count = doc["n"]   | 0;
        S.pos   = doc["pos"] | 0;
        S.dur   = doc["dur"] | 0;
        copyStr(S.med, sizeof(S.med), doc["med"]);
    }
    else if (!strcmp(t, "vol")) {
        if (millis() > S.volSuppressUntil)
            S.vol = doc["v"] | 0;
        S.mute = (doc["mute"] | 0) != 0;
        S.loop = doc["loop"] | 0;
    }
    else if (!strcmp(t, "net")) {
        S.rssi = doc["rssi"] | 0;
        copyStr(S.ssid, sizeof(S.ssid), doc["ssid"]);
        copyStr(S.ip, sizeof(S.ip), doc["ip"]);
        if (fromSerial) netLearnSsid(S.ssid);   // the show's SSID, learned from a player over USB only
    }
    else if (!strcmp(t, "list")) {
        uint8_t g = doc["g"] | 0;
        if (g != S.listGen) {           // new generation -> reset table
            S.listGen = g;
            S.listLoaded = 0;
            S.listScroll = 0;
        }
        S.listTotal = doc["n"] | 0;
        int i = doc["i"] | 0;
        if (i > (int)S.listLoaded) {    // gap: a chunk was lost -> re-request the dump
            if (millis() - lastResync > 2000) {
                lastResync = millis();
                sendCmd("getall");
            }
            return;
        }
        for (JsonVariantConst it : doc["items"].as<JsonArrayConst>()) {
            if (i >= LIST_MAX) break;
            copyStr(S.list[i], NAME_LEN, it);
            i++;
        }
        if (i > (int)S.listLoaded) S.listLoaded = i;
    }
    else if (!strcmp(t, "peers")) {
        S.peersTotal = doc["n"] | 0;
        int i = doc["i"] | 0;
        if (i == 0) S.peersN = 0;       // chunks arrive in order, first one resets
        for (JsonObjectConst it : doc["items"].as<JsonArrayConst>()) {
            if (i >= PEERS_MAX) break;
            copyStr(S.peers[i].nm, sizeof(S.peers[i].nm), it["nm"]);
            S.peers[i].lk = it["lk"] | 0;
            S.peers[i].me = (it["me"] | 0) != 0;
            i++;
        }
        if (i > (int)S.peersN) S.peersN = i;
    }
    else if (!strcmp(t, "hello")) {
        S.proto = doc["proto"] | 0;
        copyStr(S.hostName, sizeof(S.hostName), doc["name"]);
        copyStr(S.hostIp, sizeof(S.hostIp), doc["ip"]);
    }
    else if (!strcmp(t, "bye")) {
        S.byed = true;
        S.linked = false;
        if (!fromSerial) netDrop("player bye");   // its player shuts down: fail over now
    }

    S.dBar = S.dPage = true;
}

void linkBegin() {
    char chip[16];
    snprintf(chip, sizeof(chip), "%012llX", (unsigned long long)ESP.getEfuseMac());
    snprintf(helloLine, sizeof(helloLine), "hello " STR(PROTO_VERSION) " " STR(FW_VERSION) " %s", chip);
    Serial.setRxBufferSize(4096);       // full dump bursts ~11KB; HWCDC drops on overflow
    Serial.begin(115200);
    bootAt = millis();
    serialLine(helloLine);
    lastHello = millis();
}

void linkLoop() {
    uint8_t chunk[256];
    int n;
    while ((n = Serial.available()) > 0) {
        if (n > (int)sizeof(chunk)) n = sizeof(chunk);
        n = Serial.read(chunk, n);      // bulk drain, keeps the ring buffer free during bursts
        for (int k = 0; k < n; k++) {
            char c = (char)chunk[k];
            if (c == '\n') {
                if (!overflow && bufLen) {
                    buf[bufLen] = 0;
                    linkParse(buf, true);
                }
                bufLen = 0;
                overflow = false;
            } else if (c != '\r') {
                if (bufLen < RX_BUF - 1) buf[bufLen++] = c;
                else overflow = true;   // oversize line: discard to next newline
            }
        }
    }

    uint32_t now = millis();

    // transport: the USB wins whenever a player talks on it; otherwise wireless
    if (S.mode == MODE_BOOT) {
        if (!S.vbus || now - bootAt > USB_LISTEN_MS) setMode(MODE_NET);
    } else if (S.mode == MODE_USB) {
        if (!S.vbus || now - lastSerialRx > STALE_MS) setMode(MODE_NET);   // unplugged / player silent
    }

    // hello beacon on the USB while no player holds it (doubles as dump request); on VBUS only:
    // without it there is no host to hear it
    if (S.vbus && !(S.mode == MODE_USB && S.linked) && now - lastHello > HELLO_MS) {
        lastHello = now;
        serialLine(helloLine);
    }

    if (S.mode == MODE_NET) netLoop();
}
