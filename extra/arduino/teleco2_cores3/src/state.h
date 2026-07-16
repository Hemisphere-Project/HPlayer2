#pragma once
#include <stdint.h>

#define LIST_MAX    200
#define NAME_LEN    52
#define PEERS_MAX   24

struct Peer {
    char    nm[20];
    uint8_t lk;         // zyre link: 0 GONE / 1 SILENT / 2 EVASIVE / 3 OK
    bool    me;         // the player we are plugged into
};

struct AppState {
    // link
    bool     linked = false;
    bool     byed = false;              // host said bye (clean shutdown)
    uint32_t lastRx = 0;
    int      proto = 0;
    char     hostName[32] = "";
    char     hostIp[16] = "";

    // player
    uint8_t  pl = 0;                    // 0 stop / 1 play / 2 pause
    char     med[NAME_LEN] = "";
    int      idx = -1;                  // -1 = no track selected
    int      count = 0;
    int      pos = 0, dur = 0;          // seconds

    // settings
    int      vol = 0;
    bool     mute = false;
    int      loop = 0;
    uint32_t volSuppressUntil = 0;      // ignore inbound vol after local volup/voldown

    // network (host side)
    char     ssid[24] = "";
    int      rssi = 0;
    char     ip[16] = "";

    // media list
    uint8_t  listGen = 255;
    uint16_t listTotal = 0;             // host-side total (may exceed LIST_MAX)
    uint16_t listLoaded = 0;
    char     list[LIST_MAX][NAME_LEN];

    // peers
    uint8_t  peersN = 0;                // entries loaded
    uint8_t  peersTotal = 0;            // host-side count
    Peer     peers[PEERS_MAX];

    // ui
    bool     locked = true;             // boots locked: hold [PLAY]+[PEERS] to unlock
    uint8_t  toastKind = 0;             // TOAST_* (ui.h), 0 = none
    uint32_t toastUntil = 0;
    uint8_t  page = 0;                  // 0 transport / 1 media / 2 peers
    int      listScroll = 0;            // first visible media row

    // dirty flags
    bool     dBar = true;
    bool     dPage = true;
};

extern AppState S;
