#include <Arduino.h>
#include <ArduinoJson.h>
#include "state.h"
#include "link.h"

#define RX_BUF      640
#define STALE_MS    8000
#define HELLO_MS    3000

#define STR_(x)     #x
#define STR(x)      STR_(x)

static char     buf[RX_BUF];
static size_t   bufLen = 0;
static bool     overflow = false;
static uint32_t lastHello = 0;

void sendCmd(const char* cmd) {
    Serial.print(cmd);
    Serial.print('\n');
}

void sendCmdi(const char* cmd, int arg) {
    Serial.printf("%s %d\n", cmd, arg);
}

static void copyStr(char* dst, size_t cap, JsonVariantConst v) {
    strlcpy(dst, v | "", cap);
}

static void parseLine(const char* line) {
    JsonDocument doc;
    if (deserializeJson(doc, line) != DeserializationError::Ok) return;  // boot spew, noise..
    const char* t = doc["t"] | "";
    if (!*t) return;

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
    }

    S.dBar = S.dPage = true;
}

void linkBegin() {
    Serial.setRxBufferSize(1024);
    Serial.begin(115200);
    sendCmd("hello " STR(PROTO_VERSION));
    lastHello = millis();
}

void linkLoop() {
    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\n') {
            if (!overflow && bufLen) {
                buf[bufLen] = 0;
                parseLine(buf);
            }
            bufLen = 0;
            overflow = false;
        } else if (c != '\r') {
            if (bufLen < RX_BUF - 1) buf[bufLen++] = c;
            else overflow = true;       // oversize line: discard to next newline
        }
    }

    if (S.linked && millis() - S.lastRx > STALE_MS) {   // host gone silent
        S.linked = false;
        S.dBar = S.dPage = true;
    }

    if (!S.linked && millis() - lastHello > HELLO_MS) { // beacon doubles as dump request
        lastHello = millis();
        sendCmd("hello " STR(PROTO_VERSION));
    }
}
