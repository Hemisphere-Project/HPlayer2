#pragma once

// Power (fw 6, hplayer2#t-090): battery %, charging, VBUS; on WiFi (MODE_NET) the screen dims after
// 20 s idle (the waking touch is swallowed: it never presses a button) and re-locks after 2 min;
// 10 min without WiFi on battery -> the screen says so, then the AXP2101 powers the remote off.
// MODE_USB keeps fw 5's screen: never dims, never re-locks by itself.

#define BRIGHT_DIM          48          // 24 read as off, 64 a bit much (Thomas, bench 2026-11-07)
#define DIM_MS              20000UL
#define LOCK_ON_DIM         0           // Thomas 2026-11-06: no; re-lock after LOCK_AFTER_IDLE_MS
#define LOCK_AFTER_IDLE_MS  120000UL
#ifndef OFF_AFTER_S
#define OFF_AFTER_S         600         // 10 min without WiFi on battery (bench: -DOFF_AFTER_S=60)
#endif
#define OFF_WARN_S          60          // countdown on screen for the last minute

void powerBegin();
void powerLoop();
bool powerWake();       // on a touch press: true = the screen was dimmed, swallow this touch
void powerActivity();   // any other reason to be bright (mode change, a host event...)
