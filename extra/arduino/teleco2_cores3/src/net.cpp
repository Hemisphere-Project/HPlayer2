#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <Preferences.h>
#include <ArduinoJson.h>
#include "state.h"
#include "link.h"
#include "net.h"

#define PROBE_PORT      3739    // teleco2 discovery (players answer here) — NEVER 3738, the clock's
#define LOCAL_UDP       3741    // our own UDP port (replies come back here)
#define DEFAULT_SSID    "pisync"
#define PROBE_MS        400     // collect "here" replies this long
#define REPROBE_MS      800     // nobody answered / connect failed: probe again after
#define CONNECT_MS      1500    // TCP connect timeout
#define HB_MS           1000    // our heartbeat
#define DEAD_MS         3000    // no host line this long: the session is dead
#define WIFI_RETRY_MS   6000    // association attempt budget
#define LEADER_RSSI     50      // attach to the clock leader only with at least this signal (0..100)
#define CANDS_MAX       24
#define RX_BUF          640

struct Cand {
    IPAddress ip;
    uint16_t  port;
    char      nm[20];
    uint8_t   lead;
    int       rssi;
};

static Cand        cands[CANDS_MAX];
static uint8_t     candsN = 0;
static WiFiUDP     udp;
static WiFiClient  cli;
static Preferences prefs;

static bool     enabled = false;
static bool     udpUp = false;
static char     ssid[33] = DEFAULT_SSID;
static char     lastUsed[20] = "";
static uint8_t  bssid[6];
static int32_t  chan = 0;
static bool     haveFast = false;       // bssid + channel of the last association (fast reconnect)
static uint8_t  wifiFails = 0;
static uint32_t wifiTryAt = 0;
static bool     probing = false;
static uint32_t probeUntil = 0;
static uint32_t nextProbe = 0;
static uint32_t lastHb = 0;
static uint32_t lastNetRx = 0;
static char     cur[20] = "";           // the attached (or last tried) player
static char     avoid[20] = "";         // a player that said bye: skipped for AVOID_MS
static uint32_t avoidUntil = 0;
#define AVOID_MS        15000

static char     rx[RX_BUF];
static size_t   rxLen = 0;
static bool     rxOver = false;

const char* netPlayer() { return cur; }
const char* netSsid() { return ssid; }

static int toPct(int dbm) {             // -100 dBm -> 0, -50 dBm -> 100
    int p = 2 * (dbm + 100);
    return p < 0 ? 0 : p > 100 ? 100 : p;
}

void netBegin() {
    prefs.begin("teleco2", false);
    String s = prefs.getString("ssid", DEFAULT_SSID);
    strlcpy(ssid, s.length() ? s.c_str() : DEFAULT_SSID, sizeof(ssid));
    strlcpy(lastUsed, prefs.getString("last", "").c_str(), sizeof(lastUsed));
    if (prefs.getBytes("bssid", bssid, 6) == 6) {
        chan = prefs.getInt("chan", 0);
        haveFast = chan > 0;
    }
    WiFi.persistent(false);             // our NVS keys, not the driver's
    WiFi.mode(WIFI_OFF);
}

static void startWifi() {
    if (haveFast && wifiFails < 2) WiFi.begin(ssid, NULL, chan, bssid);   // last AP, its channel
    else WiFi.begin(ssid);              // open network; a hidden SSID is found by name, never by scan
    wifiTryAt = millis();
}

static void closeSession(const char* why) {
    if (cli.connected()) cli.stop();
    rxLen = 0;
    rxOver = false;
    S.linked = false;
    if (S.net == NET_LINK) S.net = NET_SEARCH;
    probing = false;
    nextProbe = millis();
    S.dBar = S.dPage = true;
    (void)why;
}

void netDrop(const char* why) {
    if (!enabled) return;
    if (!strcmp(why, "player bye")) {   // it shuts down: its probe responder may answer a moment more
        strlcpy(avoid, cur, sizeof(avoid));
        avoidUntil = millis() + AVOID_MS;
    }
    closeSession(why);
}

void netEnable(bool on) {
    if (on == enabled) return;
    enabled = on;
    if (on) {
        WiFi.mode(WIFI_STA);
        WiFi.setSleep(true);            // modem sleep between DTIMs (battery)
        WiFi.setAutoReconnect(false);   // we drive the retries (fast channel first)
        S.net = NET_NOWIFI;
        S.noWifiSince = millis();
        wifiFails = 0;
        startWifi();
    } else {
        closeSession("usb");
        if (udpUp) { udp.stop(); udpUp = false; }
        WiFi.disconnect(true);
        WiFi.mode(WIFI_OFF);
        S.net = NET_OFF;
        S.noWifiSince = 0;
        S.heard = 0;
    }
    S.dBar = S.dPage = true;
}

void netLearnSsid(const char* s) {
    if (!s || !*s || !strcmp(s, ssid) || strlen(s) >= sizeof(ssid)) return;
    strlcpy(ssid, s, sizeof(ssid));
    prefs.putString("ssid", ssid);
    haveFast = false;                   // another network: forget the last AP
    prefs.remove("bssid");
}

void netPin(const char* name) {
    if (!strcmp(S.pinned, name)) S.pinned[0] = 0;      // tap again: unpin
    else strlcpy(S.pinned, name, sizeof(S.pinned));
    if (S.pinned[0] && S.net == NET_LINK && strcmp(S.pinned, cur)) closeSession("pinned another player");
    S.dBar = S.dPage = true;
}

void netSend(const char* line) {
    if (!enabled || S.net != NET_LINK || !cli.connected()) return;     // never queued
    cli.print(line);
    cli.print('\n');
}

//
// discovery
//

static void sendProbe() {
    char msg[64];                       // "find <proto> <fw> <chipid>": the hello's own words
    snprintf(msg, sizeof(msg), "find%s", strchr(linkHello(), ' '));
    IPAddress dests[2] = {WiFi.broadcastIP(), IPAddress(255, 255, 255, 255)};
    for (auto& d : dests) {
        udp.beginPacket(d, PROBE_PORT);
        udp.print(msg);
        udp.endPacket();
    }
    candsN = 0;
    probing = true;
    probeUntil = millis() + PROBE_MS;
}

static void collect() {
    char b[256];
    int len;
    while ((len = udp.parsePacket()) > 0) {
        int r = udp.read(b, sizeof(b) - 1);
        if (r <= 0) continue;
        b[r] = 0;
        JsonDocument doc;
        if (deserializeJson(doc, b) != DeserializationError::Ok) continue;
        if (strcmp(doc["t"] | "", "here")) continue;
        const char* nm = doc["nm"] | "";
        if (!*nm) continue;
        int k;
        for (k = 0; k < candsN; k++) if (!strcmp(cands[k].nm, nm)) break;   // one entry per player
        if (k == candsN) {
            if (candsN >= CANDS_MAX) continue;
            candsN++;
        }
        cands[k].ip = udp.remoteIP();
        cands[k].port = doc["port"] | 3740;
        strlcpy(cands[k].nm, nm, sizeof(cands[k].nm));
        cands[k].lead = doc["lead"] | 0;
        cands[k].rssi = doc["rssi"] | 0;
    }
}

static bool avoided(int k) {
    return avoid[0] && (int32_t)(millis() - avoidUntil) < 0 && !strcmp(cands[k].nm, avoid);
}

static int byName(const char* nm) {
    if (!nm || !*nm) return -1;
    for (int k = 0; k < candsN; k++) if (!strcmp(cands[k].nm, nm) && !avoided(k)) return k;
    return -1;
}

static int choose() {
    int k;
    if ((k = byName(S.pinned)) >= 0) return k;          // tap-to-pin
    if ((k = byName(cur)) >= 0) return k;               // stay on the current one while it answers
    if ((k = byName(lastUsed)) >= 0) return k;          // the last used
    int best = -1;
    for (k = 0; k < candsN; k++)                        // the clock leader, if its signal is good
        if (cands[k].lead && cands[k].rssi >= LEADER_RSSI && !avoided(k)) return k;
    for (k = 0; k < candsN; k++)                        // the best signal
        if (!avoided(k) && (best < 0 || cands[k].rssi > cands[best].rssi)) best = k;
    return best;
}

static bool attach(int k) {
    strlcpy(cur, cands[k].nm, sizeof(cur));
    S.dBar = S.dPage = true;
    if (!cli.connect(cands[k].ip, cands[k].port, CONNECT_MS)) return false;
    cli.setNoDelay(true);               // a key press is one small line: no Nagle wait
    rxLen = 0;
    rxOver = false;
    S.net = NET_LINK;
    lastNetRx = lastHb = millis();
    cli.print(linkHello());             // the player dumps everything on hello
    cli.print('\n');
    if (strcmp(lastUsed, cur)) {
        strlcpy(lastUsed, cur, sizeof(lastUsed));
        prefs.putString("last", lastUsed);
    }
    return true;
}

//
// loop
//

void netLoop() {
    if (!enabled) return;
    uint32_t now = millis();

    if (WiFi.status() != WL_CONNECTED) {
        if (S.net != NET_NOWIFI) {
            closeSession("wifi lost");
            S.net = NET_NOWIFI;
            S.noWifiSince = now;
            S.heard = 0;
            S.dBar = S.dPage = true;
        }
        if (now - wifiTryAt > WIFI_RETRY_MS) {
            if (wifiFails < 255) wifiFails++;
            WiFi.disconnect();
            startWifi();
        }
        return;
    }

    if (S.net == NET_NOWIFI) {          // just associated
        wifiFails = 0;
        S.noWifiSince = 0;
        const uint8_t* b = WiFi.BSSID();
        int32_t c = WiFi.channel();
        if (b && c > 0 && (!haveFast || c != chan || memcmp(b, bssid, 6))) {
            memcpy(bssid, b, 6);
            chan = c;
            haveFast = true;
            prefs.putBytes("bssid", bssid, 6);
            prefs.putInt("chan", chan);
        }
        if (!udpUp) udpUp = udp.begin(LOCAL_UDP);
        S.net = NET_SEARCH;
        nextProbe = now;
        S.dBar = S.dPage = true;
    }

    static uint32_t lastRssi = 0;
    if (now - lastRssi > 2000) {
        lastRssi = now;
        int p = toPct(WiFi.RSSI());
        if (p != S.wifiRssi) { S.wifiRssi = p; S.dBar = true; }
    }

    if (S.net == NET_SEARCH) {
        if (!probing && (int32_t)(now - nextProbe) >= 0) sendProbe();
        if (probing) {
            collect();
            if ((int32_t)(now - probeUntil) >= 0) {
                probing = false;
                S.heard = candsN;
                S.dPage = true;
                int k = choose();
                if (k < 0 || !attach(k)) nextProbe = millis() + REPROBE_MS;
            }
        }
        return;
    }

    // NET_LINK: read lines, heartbeat, dead link
    while (cli.available() > 0) {
        int c = cli.read();
        if (c < 0) break;
        if (c == '\n') {
            if (!rxOver && rxLen) {
                rx[rxLen] = 0;
                lastNetRx = millis();
                linkParse(rx, false);
                if (S.net != NET_LINK) return;  // the line closed the session (bye)
            }
            rxLen = 0;
            rxOver = false;
        } else if (c != '\r') {
            if (rxLen < RX_BUF - 1) rx[rxLen++] = (char)c;
            else rxOver = true;
        }
    }
    now = millis();
    if (!cli.connected() || now - lastNetRx > DEAD_MS) {
        closeSession("dead");
        return;
    }
    if (now - lastHb >= HB_MS) {
        lastHb = now;
        netSend("hb");
    }
}
