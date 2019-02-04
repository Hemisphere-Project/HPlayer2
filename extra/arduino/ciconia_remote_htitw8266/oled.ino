#include <U8x8lib.h>

// Pin 16   OLED Reset
// Pin 4,5  I2C
U8X8_SSD1306_128X32_UNIVISION_HW_I2C u8x8(16);

String lastdisp;

void oled_init() {
  u8x8.begin();
}

void oled_hello() {
  u8x8.setFont(u8x8_font_chroma48medium8_r);
  u8x8.draw2x2String(0,0,"Hello");
  u8x8.draw2x2String(0,2,"World");
}

void oled_clear2() {
  u8x8.draw2x2String(0,2,"        ");
}

/*
 * Show status
 */
void oled_status(String stat) {
  oled_status(stat, "       ");
}
void oled_status(String stat, String stat2) {

  if (stat+stat2 == lastdisp) return;
  
  u8x8.clear();
  lastdisp = stat+stat2;
  u8x8.setFont(u8x8_font_amstrad_cpc_extended_f);
  
  //if (stat.length() > 11) display.setFont(ArialMT_Plain_16);
  //else display.setFont(ArialMT_Plain_24);
  u8x8.draw2x2String(0,0,stat.substring(0,8).c_str());

  //if (stat2.length() > 11) display.setFont(ArialMT_Plain_16);
  //else display.setFont(ArialMT_Plain_24);
  u8x8.draw2x2String(0,2,stat2.substring(0,8).c_str());
}
