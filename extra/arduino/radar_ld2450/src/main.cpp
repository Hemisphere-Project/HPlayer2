// radar_ld2450 — read an HLK-LD2450 over UART, forward its targets to HPlayer2 over USB.
//
// Dumb by design (Thomas, 2026-07-13): no range, no threshold, no hysteresis here —
// nobody reflashes 6 sealed IP55 boxes on site. Every decision lives on the Pi, in
// core/interfaces/radar.py. This just decodes LD2450 frames and prints one line per
// frame on the USB CDC:
//
//     T <x1>,<y1>,<v1> <x2>,<y2>,<v2> ...     (only active targets; bare "T" = empty)
//
// x,y in mm (x = lateral, signed; y = distance, forward-positive), v = speed in cm/s.

#include <Arduino.h>

#ifndef RADAR_RX
#define RADAR_RX 20
#endif
#ifndef RADAR_TX
#define RADAR_TX 21
#endif
#ifndef LED_PIN
#define LED_PIN 8
#endif
#ifndef LED_ACTIVE_LOW
#define LED_ACTIVE_LOW 1
#endif
#if LED_ACTIVE_LOW
#define LED_ON LOW
#define LED_OFF HIGH
#else
#define LED_ON HIGH
#define LED_OFF LOW
#endif

#define STR_(x) #x
#define STR(x) STR_(x)

#if LED_MATRIX
// Desk-debug display (env:atom, M5 Atom Matrix): each raw target plotted on the
// 5x5 grid — x ±2 m -> column, y 0..4 m -> row (radar at the top edge), one color
// per LD2450 slot. Dim red center dot = frames flowing but zone empty. Display
// only, still zero decisions here; the production C3 box compiles without this.
#include <FastLED.h>
static CRGB leds[25];
static const CRGB SLOT_COLOR[3] = {CRGB::Green, CRGB::Blue, CRGB::Yellow};
#endif

// LD2450 target frame: AA FF 03 00 | 3 targets x 8 bytes | 55 CC  = 30 bytes.
static const uint8_t HDR[4] = {0xAA, 0xFF, 0x03, 0x00};
static const int FRAME_LEN = 30;
static uint8_t buf[FRAME_LEN];
static int idx = 0;

// LD2450 sign-magnitude: bit15 set = positive, magnitude in the low 15 bits.
static int decode(uint8_t lo, uint8_t hi) {
  uint16_t raw = (uint16_t)lo | ((uint16_t)hi << 8);
  int mag = raw & 0x7FFF;
  return (raw & 0x8000) ? mag : -mag;
}

static void emitFrame(const uint8_t* f) {
  String line = "T";
  bool anyActive = false;
#if LED_MATRIX
  FastLED.clear();
#endif
  for (int t = 0; t < 3; t++) {
    const uint8_t* p = f + 4 + t * 8;
    int x = decode(p[0], p[1]);
    int y = decode(p[2], p[3]);
    int v = decode(p[4], p[5]);
    uint16_t res = (uint16_t)p[6] | ((uint16_t)p[7] << 8);
    if (x == 0 && y == 0 && res == 0) continue;   // empty slot -> LD2450 zeroes it
    anyActive = true;
    line += ' ';
    line += x; line += ','; line += y; line += ','; line += v;
#if LED_MATRIX
    int col = constrain((x + 2000) / 800, 0, 4);  // x: -2 m .. +2 m
    int row = constrain(y / 800, 0, 4);           // y: 0 .. 4 m, radar = top row
    leds[row * 5 + col] = SLOT_COLOR[t];
#endif
  }
  Serial.println(line);
#if LED_MATRIX
  if (!anyActive) leds[12] = CRGB(16, 0, 0);      // heartbeat: frames flow, zone empty
  FastLED.show();
#else
  digitalWrite(LED_PIN, anyActive ? LED_ON : LED_OFF);
#endif
}

void setup() {
#if LED_MATRIX
  FastLED.addLeds<WS2812, LED_PIN, GRB>(leds, 25);
  FastLED.setBrightness(20);                      // 25 LEDs on USB power — keep it low
  leds[0] = CRGB::Blue;                           // boot dot: alive but no radar frame yet;
  FastLED.show();                                 // the first valid frame overwrites it
#else
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LED_OFF);
#endif

  Serial.begin(115200);                                    // USB CDC to the Pi
  Serial1.begin(256000, SERIAL_8N1, RADAR_RX, RADAR_TX);   // LD2450 ships at 256000 baud

  Serial.println("hello " STR(PROTO_VERSION));
}

void loop() {
  while (Serial1.available()) {
    uint8_t b = Serial1.read();
    if (idx < 4) {
      // still syncing on the header
      if (b == HDR[idx]) buf[idx++] = b;
      else { idx = (b == HDR[0]) ? 1 : 0; if (idx == 1) buf[0] = b; }
    } else {
      buf[idx++] = b;
      if (idx == FRAME_LEN) {
        idx = 0;
        if (buf[28] == 0x55 && buf[29] == 0xCC) emitFrame(buf);
      }
    }
  }
}
