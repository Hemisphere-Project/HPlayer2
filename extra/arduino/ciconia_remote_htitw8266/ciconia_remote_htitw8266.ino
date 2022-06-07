/*
   SETTINGS
*/
#define CR_VERSION  0.01  // Init
#define CR_VERSION  0.02  // 1watt teleco
#define CR_VERSION  0.03  // 1watt teleco
#define CR_VERSION  0.04  // settings EEPROM

#define SLEEPTIME 3       // minutes before going to sleep

#include <Arduino.h>
#include <OSCMessage.h> //https://github.com/stahlnow/OSCLib-for-ESP8266
#include "debug.h"
#include "wifi.h"

bool shuttingDown = false;

//UDP
WiFiUDP udp_in;
WiFiUDP udp_out;
char udpPacket[1472];

long lastInfo = 0;
long lastNews = 0;

// IP
String myIP = "3.0.0.";

String hostIP = "3.0.0.1";
int hostPORT_http = 8037;
int hostPORT_osc = 4000;
int remotePORT_osc = 4001;

// Pinout: {media1, media2, media3, media4, push, dec, inc}
// SCL = 14 / SDA = 2 / RX = 3 / TX = 1
//
int *pins;
int pinout[1][2] = {  {3, 13}                           // model 0 : ciconia 1                   
                      //{D3, D7, D6, 14, 2, 3, 1}    
                    };


void ICACHE_RAM_ATTR trig0() {
  event_trigger(pins[0], next);
};

void ICACHE_RAM_ATTR trig1() {
  event_trigger(pins[1], prev);
};

void setup(void) {
  LOGSETUP();
  LOG("hello");

  // Settings config
  String keys[16] = {"id", "model"};
  settings_load( keys );

  // Settings SET EEPROM !
  //settings_set("id", 2);
  //settings_set("model", 0);   // 0: remote ciconia 

  // Oled
  oled_init();
  oled_status("hello");

  // Wifi
  myIP += String(settings_get("id")+100);
  wifi_static(myIP);
  wifi_connect("ciconia");
  wifi_ota( "ciconia v" + String(CR_VERSION, 2) );
  wifi_onConnect(doOnConnect);
  wifi_onDisconnect(doOnDisconnect);

  // HTTP client
  http_init();

  // INPUTS
  pins = pinout[settings_get("model")];

  // SET PULLUP
  for(int k=0; k<2; k++) pinMode(pins[k], INPUT_PULLUP);
  
  // next 
  attachInterrupt(digitalPinToInterrupt(pins[0]), trig0, FALLING);

  // prev
  attachInterrupt(digitalPinToInterrupt(pins[1]), trig1, FALLING);

  //UDP
  // input socket
  udp_in.begin(remotePORT_osc);
}

void loop(void) {
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
}


/*
   on Connect
*/
void doOnConnect() {
  oled_status("-wifi ok");
}

/*
   on Disconnect
*/
void doOnDisconnect() {
  if (!shuttingDown) oled_status("-no wifi");
}

void next() {
  http_get("/next");
}

void prev() {
  http_get("/prev");
}

void shutdown() {
  shuttingDown = true;
  wifi_disarm();
  oled_status("          ", "          ");
  WiFi.mode(WIFI_OFF);
  ESP.wdtDisable();
  ESP.deepSleep(0);
}
