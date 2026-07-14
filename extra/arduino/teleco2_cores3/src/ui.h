#pragma once
#include <M5Unified.h>

// 320x240 layout: status bar / page area / tab bar
#define SCREEN_W    320
#define SCREEN_H    240
#define BAR_H       28
#define TAB_H       30
#define PAGE_Y      BAR_H
#define PAGE_H      (SCREEN_H - BAR_H - TAB_H)
#define TAB_Y       (SCREEN_H - TAB_H)

#define ROW_H       26

// cassette-futurist palette (RGB565): phosphor hues on black,
// one hue per information class so it stays readable in live conditions:
// paper = names/content, green = play/ok, red = stop/error, cyan = network,
// amber = chrome/volume/selection
#define C_BG        0x0000
#define C_AMBER     0xFD80      // #FFB000 — chrome, outlines, volume
#define C_DIM       0x7AC0      // #7F5800 — inactive amber
#define C_GREEN     0x37E6      // #33FF33 — playing / ok
#define C_RED       0xF800      // stop / error / mute
#define C_CYAN      0x071F      // #00E0FF — network (rssi, peers, host)
#define C_PAPER     0xF739      // #F5E6C8 — warm white, content text
#define C_PANEL     0x20E2      // warm near-black panel fill
#define C_LINE      0x39A5      // warm grey rules

// fonts (M5GFX built-ins): mono for the deck look, 7-seg for readouts
#define F_MONO      (&fonts::FreeMonoBold9pt7b)
#define F_MONO_BIG  (&fonts::FreeMonoBold12pt7b)
#define F_MICRO     (&fonts::Font0)
#define F_7SEG      (&fonts::Font7)

#define BRIGHT_NORMAL   200
#define BRIGHT_LOCKED   30

void uiBegin();
void uiLoop();

// pages.cpp
void drawTransport(M5Canvas& c);
void drawMedia(M5Canvas& c);
void drawPeers(M5Canvas& c);
void tapTransport(int x, int y);        // page-local coords
void tapMedia(int x, int y);
void mediaScroll(int dyPx);
