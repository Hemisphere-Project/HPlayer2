#pragma once

// TELECO2 over WiFi (fw 6, hplayer2#t-090): the remote on its battery joins the show's WiFi
// (learned from a player over USB, `pisync` by default; open network), finds players with a UDP
// probe and holds ONE TCP session with protocol v1 lines (player side: teleco2.py, netport 3740).
//
//   discovery  UDP broadcast "find <proto> <fw> <chipid>" -> port 3739, players answer
//              {"t":"here","nm","port","lead","rssi","fw"}
//   attach     pinned (tap on PEERS) -> the current one -> the last used -> the clock leader if its
//              signal is good (an order then does not move the clock) -> the best signal
//   session    "hello 1 6 <chipid>", the player dumps; "hb" every 1 s; no host line for 3 s =
//              dead: buttons disabled (never queued), probe again, attach (target <= 5 s)
//
// Never a byte on the wallclock port (3738): a stray packet there would corrupt the clock.

void netBegin();
void netEnable(bool on);                // MODE_NET: WiFi up; else WiFi OFF
void netLoop();
void netSend(const char* line);         // dropped unless a session is alive
void netDrop(const char* why);          // close the session and fail over
void netLearnSsid(const char* ssid);    // from a player's "net" over USB
void netPin(const char* name);          // tap-to-pin (toggles)
const char* netPlayer();                // the attached (or last tried) player's name
const char* netSsid();                  // the SSID we join
