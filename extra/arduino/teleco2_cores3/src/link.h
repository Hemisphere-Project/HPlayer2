#pragma once

// TELECO2 protocol v1 — device side.
// Wire spec (authoritative copy): core/interfaces/teleco2.py header.
// host -> device : NDJSON lines (hello / st / vol / list / peers / net / bye)
// device -> host : plain text "CMD [intarg]" lines
// stale: no valid host line for 8s -> unlinked, hello beacon every 3s

void linkBegin();
void linkLoop();
void sendCmd(const char* cmd);
void sendCmdi(const char* cmd, int arg);
