#include "AXP192.h"
#include <WiFi.h>


void oled_init() {

  // initialize the M5StickC object

  if (MODEL == 3) {
    M5.Lcd.setRotation(1);
    M5.Axp.ScreenBreath(11);
    M5.Lcd.fillScreen(BLACK);

  }
  else if (MODEL == 4) {
    M5.Lcd.setRotation(3);
    M5.Axp.ScreenBreath(9);
    M5.Lcd.fillScreen(BLACK);
  }
}


String lastStat = "";
String lastStat2 = "";
String lastSys = "";

/*
 * Show status
 */
void oled_status(String stat, String stat2) {
  
  String sys = "Bat. " + String( int((M5.Axp.GetBatVoltage()-3)*100/1.19) );
  // String sys = "Bat. " + String( M5.Axp.GetBatVoltage() );

  if (WiFi.RSSI() != 0)
    sys += "  Wifi. "  + String( map(WiFi.RSSI(), -95, -30, 0, 100) );

  if (sys == lastSys && stat == lastStat && stat2 == lastStat2) return;


  M5.Lcd.fillScreen(BLACK);
  M5.Lcd.setTextColor(GREEN);

  if (MODEL == 3) M5.Lcd.setTextSize(2);
  else if (MODEL == 4)  M5.Lcd.setTextSize(3);


  if (MODEL == 3) M5.Lcd.setCursor(10, 10);
  else if (MODEL == 4)  M5.Lcd.setCursor(10, 20);

  M5.Lcd.printf(stat.c_str());

  if (MODEL == 3) M5.Lcd.setCursor(90, 40);
  else if (MODEL == 4)  M5.Lcd.setCursor(140, 65);

  M5.Lcd.setTextColor(WHITE);
  M5.Lcd.printf(stat2.c_str());

  if (MODEL == 3) {
    M5.Lcd.setTextSize(1.2);
    M5.Lcd.setCursor(10, 65);
  }
  else if (MODEL == 4)  {
    M5.Lcd.setTextSize(2);
    M5.Lcd.setCursor(10,110);
  }

  M5.Lcd.setTextColor(RED);
  M5.Lcd.printf(sys.c_str());
  
  lastSys = sys;
  lastStat = stat;
  lastStat2 = stat2;
}
void oled_status(String stat) {
  oled_status(stat, "       ");
}