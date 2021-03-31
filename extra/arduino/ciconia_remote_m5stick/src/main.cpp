#include <Arduino.h>
#include "debug.h"
#include "M5StickC.h"
#include "oled.h"
#include "settings.h"
#include "events.h"
#include "tools.h"
#include "wifi.h"
#include "osc.h"
#include "http.h"
#include "actions.h"

#define CR_VERSION  0.10  // M5stick

// IP
String myIP = "3.0.0.";

#define SLEEPTIME 3       // minutes before going to sleep



long lastInfo = 0;
long lastNews = 0;

void setup() {
  M5.begin();
  oled_init();
  oled_status("Ciconia");
  // delay(1000);

  // Settings config
  String keys[16] = {"id", "model"};
  settings_load( keys );

  // Settings SET EEPROM !
  settings_set("id", 10);
  settings_set("model", 3);   // 0: remote ciconia   1: ttgo   2: htit   3: M5stickC

  // Wifi
  myIP += String(settings_get("id")+100);
  wifi_static(myIP);
  wifi_connect("ciconia");
  wifi_ota( "ciconia v" + String(CR_VERSION, 2) );
  wifi_onConnect(doOnConnect);
  wifi_onDisconnect(doOnDisconnect);

  // HTTP client
  http_init();

  // OSC
  osc_init();
  
  
}

void loop() {
  event_loop();

  if (wifi_isok()) {
    wifi_otaCheck();

    if (udp_in.parsePacket()) {
      int len = udp_in.read(udpPacket, 1470);
      if (len >= 0) {
        udpPacket[len] = 0;
        LOGF("UDP: packet received: %s\n", udpPacket);
        if (udpPacket[0] != '/') {
          oled_status( getValue(udpPacket, '"', 0), String("  ")+getValue(udpPacket, '"', 1) );
          lastInfo = millis();
          lastNews = millis();
        }
      }
    }

    if (millis() - lastInfo > 200) {
      // STATUS check
      LOG("sending synctest");
      udp_out.beginPacket(hostIP.c_str(), hostPORT_osc);
      OSCMessage msg("/synctest");
      msg.send(udp_out);
      udp_out.endPacket();
      lastInfo = millis() - 50;
    }

    if (millis() - lastNews > 1500) {
      oled_status("-no rpi");
    }
  }
  else {
    oled_status("+no wifi");
  }
  delay(50);

  if (millis() - lastNews > (SLEEPTIME * 60 * 1000)) {
    shutdown();
  }
  //LOG("loop");

  M5.update();
  if(M5.BtnA.wasPressed()) event_trigger(1, next);
  if(M5.BtnB.wasPressed()) event_trigger(2, prev);
  if(M5.Axp.GetBtnPress() == 0x02)  event_trigger(2, stop);
  if(M5.Axp.GetBtnPress() == 0x01)  shutdown();

}