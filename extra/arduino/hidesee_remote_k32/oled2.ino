#include <SPI.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#define SCREEN_WIDTH 128 // OLED display width, in pixels
#define SCREEN_HEIGHT 64 // OLED display height, in pixels

// Declaration for an SSD1306 display connected to I2C (SDA, SCL pins)
#define oled2_RESET     -1 // Reset pin # (or -1 if sharing Arduino reset pin)
#define I2C_SDA 32
#define I2C_SCL 33
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, oled2_RESET);

String oled_stat1 = "";
String oled_stat2 = "";
String oled_stat3 = "";

void oled2_init() {
  Wire.begin(I2C_SDA, I2C_SCL);
  display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  display.clearDisplay();
  display.display();
}

void oled2_hello() {
  display.clearDisplay();

  display.setTextSize(2);   
  display.setTextColor(BLACK, WHITE); // Draw 'inverse' text
  display.println(" h&s ");

  display.setTextSize(1);             // Draw 2X-scale text
  display.setTextColor(WHITE);
  display.println(F("\nHELLO"));
  
  display.display();
}


/*
 * Show status
 */
void oled2_status(String stat) {
  oled2_status(stat, "       ", "       ");
}

void oled2_status(String stat, String stat2) {
  oled2_status(stat, stat2, "       ");
}

void oled2_status(String stat, String stat2, String stat3) {

  oled_stat1 = stat;
  oled_stat2 = stat2;
  oled_stat3 = stat3;
  
  //if (stat.length() > 11) display.setFont(ArialMT_Plain_16);
  //else display.setFont(ArialMT_Plain_24);
  //u8x8.draw2x2String(0,0,stat.substring(0,8).c_str());

  //if (stat2.length() > 11) display.setFont(ArialMT_Plain_16);
  //else display.setFont(ArialMT_Plain_24);
  //u8x8.draw2x2String(0,2,stat2.substring(0,8).c_str());

  
}

void oled2_loop() {
  if (oled_stat1+oled_stat2+oled_stat3 == lastdisp) return;
  lastdisp = oled_stat1+oled_stat2+oled_stat3;

  LOG("display "+lastdisp);
  
  display.clearDisplay();
  display.setCursor(0, 0);
  display.setTextSize(2);
  display.setTextColor(WHITE);
  display.println(oled_stat1);

  display.setTextSize(1);
  display.println();
  display.println(oled_stat2);
  display.println();
  display.println(oled_stat3);
  
  display.display();
}

void oled2_clear() {
  display.clearDisplay();
  display.display();
}
