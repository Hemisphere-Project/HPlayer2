#include <SPI.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#define SCREEN_WIDTH 128 // OLED display width, in pixels
#define SCREEN_HEIGHT 32 // OLED display height, in pixels

// Declaration for an SSD1306 display connected to I2C (SDA, SCL pins)
#define oled2_RESET     16 // Reset pin # (or -1 if sharing Arduino reset pin)
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, oled2_RESET);

String oled_stat1 = "";
String oled_stat2 = "";

void oled2_init() {
  display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  display.clearDisplay();
  display.display();
}

void oled2_hello() {
  display.clearDisplay();

  display.setTextSize(2);   
  display.setTextColor(BLACK, WHITE); // Draw 'inverse' text
  display.println(" 1watt ");

  display.setTextSize(1);             // Draw 2X-scale text
  display.setTextColor(WHITE);
  display.println(F("\nHELLO"));
  
  display.display();
}


/*
 * Show status
 */
void oled2_status(String stat) {
  oled2_status(stat, "       ");
}
void oled2_status(String stat, String stat2) {

  oled_stat1 = stat;
  oled_stat2 = stat2;
  
  //if (stat.length() > 11) display.setFont(ArialMT_Plain_16);
  //else display.setFont(ArialMT_Plain_24);
  //u8x8.draw2x2String(0,0,stat.substring(0,8).c_str());

  //if (stat2.length() > 11) display.setFont(ArialMT_Plain_16);
  //else display.setFont(ArialMT_Plain_24);
  //u8x8.draw2x2String(0,2,stat2.substring(0,8).c_str());

  
}

void oled2_loop() {
  if (oled_stat1+oled_stat2 == lastdisp) return;
  lastdisp = oled_stat1+oled_stat2;

  LOG("display "+lastdisp);
  
  display.clearDisplay();
  display.setCursor(0, 0);
  display.setTextSize(2);
  display.setTextColor(WHITE);
  display.println(oled_stat1);

  display.setTextSize(1);
  display.println();
  display.println(oled_stat2);
  
  display.display();
}

void oled2_clear() {
  display.clearDisplay();
  display.display();
}
