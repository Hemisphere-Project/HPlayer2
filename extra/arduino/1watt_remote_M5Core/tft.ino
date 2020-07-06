

String last_s1 = "";
String last_s2 = "";
int last_bat = 0;
int last_wifi = 0;

void tft_init() {
  M5.Lcd.setBrightness(250);
  M5.Lcd.fillScreen(BLACK);
  M5.Lcd.setTextSize(2.5);
  M5.Lcd.setTextColor(WHITE);

  M5.Lcd.setCursor(30, 50);
  M5.Lcd.printf("1.WATT");

  M5.Lcd.setCursor(30, 100);
  M5.Lcd.printf("hello :)");
  
  delay(1000);
  
  M5.Lcd.fillScreen(BLACK);
}


void tft_status(String stat) {
  tft_status(stat, "       ");
}
void tft_status(String stat1, String stat2) {

  stat2.replace("Dispositifs      ", "Players");
  stat1.replace("S.", "Scene ");
  
  if (last_s1 != stat1 || last_s2 != stat2) {
    last_s1 = stat1;
    last_s2 = stat2;
    tft_draw();
  }
}

void tft_mon() {

  int rssi = WiFi.RSSI();
  if ( abs(rssi-last_wifi) > 3) {
    last_wifi = rssi;
    tft_draw();
    return;
  }

  int bat = M5.Power.getBatteryLevel();
  if ( bat != last_bat) {
    last_bat = bat;
    tft_draw();
    return;
  }
    
}

void tft_draw() {
  M5.Lcd.fillScreen(BLACK);

  M5.Lcd.setCursor(30, 50);
  M5.Lcd.printf(last_s1.c_str());

  M5.Lcd.setCursor(30, 100);
  M5.Lcd.printf(last_s2.c_str());

  
  String mon = "Wifi:";
  if (last_wifi == 0) mon += " NO!";
  else mon += String(map(last_wifi, -90, -20, 0, 100));
  mon += "   Battery:"+String(last_bat);
  
  M5.Lcd.setCursor(30, 210);
  M5.Lcd.printf(mon.c_str());
}

void tft_clear() {
   M5.Lcd.fillScreen(BLACK);
}
