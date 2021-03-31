#include "M5StickC.h"
#include "AXP192.h"
TFT_eSprite tftSprite = TFT_eSprite(&M5.Lcd); 



void oled_init() {
  // initialize the M5StickC object
  M5.Lcd.setRotation(1);
  M5.Axp.ScreenBreath(11);
  M5.Lcd.fillScreen(BLACK);

  tftSprite.createSprite(160, 80);
  tftSprite.setRotation(1);

}




/*
 * Show status
 */
void oled_status(String stat, String stat2) {
  M5.Lcd.fillScreen(BLACK);
  M5.Lcd.setTextColor(RED);
  M5.Lcd.setTextSize(2);

  M5.Lcd.setCursor(10, 10);
  M5.Lcd.printf(stat.c_str());

  M5.Lcd.setCursor(90, 40);
  M5.Lcd.setTextColor(WHITE);
  M5.Lcd.printf(stat2.c_str());

  M5.Lcd.setCursor(10, 65);
  M5.Lcd.setTextColor(GREEN);
  M5.Lcd.setTextSize(1.2);
  M5.Lcd.printf("Bat: %.2fv \r\n", M5.Axp.GetBatVoltage());
}
void oled_status(String stat) {
  oled_status(stat, "       ");
}