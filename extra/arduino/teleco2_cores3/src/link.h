#pragma once

// TELECO2 protocol v1 — device side, over the USB (fw <= 5) or over WiFi/TCP (fw >= 6).
// Wire spec (authoritative copy): core/interfaces/teleco2.py header.
// host -> device : NDJSON lines (hello / st / vol / list / peers / net / bye)
// device -> host : plain text "CMD [intarg]" lines
// USB: no valid host line for 8s -> unlinked, hello beacon every 3s (fw 5, unchanged)
// TCP: no host line for 3s -> dead, buttons disabled, failover (net.cpp)

void linkBegin();
void linkLoop();
void sendCmd(const char* cmd);              // on the active transport; dropped when none (never queued)
void sendCmdi(const char* cmd, int arg);
const char* linkHello();                    // "hello <proto> <fw> <chipid>"
void linkParse(const char* line, bool fromSerial);
