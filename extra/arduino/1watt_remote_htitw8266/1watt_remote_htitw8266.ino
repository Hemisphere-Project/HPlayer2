/*
   SETTINGS
*/
#define CR_VERSION  0.01  // Init
#define CR_VERSION  0.02  // 1watt teleco
#define CR_VERSION  0.03  // 1watt teleco
#define CR_VERSION  0.04  // settings EEPROM

#define SLEEPTIME 0       // minutes before going to sleep

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
String myIP = "10.0.0.";

String hostIP = "10.0.0.1";
int hostPORT_http = 8037;
int hostPORT_osc = 4000;

// Pinout: {media1, media2, media3, media4, push, dec, inc}
// SCL = 14 / SDA = 2 / RX = 3 / TX = 1
#define SCL 14
#define SDA 2
#define RX 3
#define TX 1
//
int *pins;
int pinout[3][7] = {  {},                           // ciconia
                      {SDA, D3, D7, SCL, D6, RX, TX},    // remote v1 (square)                        
                      {D3, D7, D6, SCL, SDA, RX, TX}     // remote v2 (inline)
                    };


void setup(void) {
  LOGSETUP();
  LOG("hello");

  // Settings config
  String keys[16] = {"id", "model"};
  settings_load( keys );

  // Settings SET EEPROM !
  settings_set("id", 4);
  settings_set("model", 2);   // 0: ciconia (2btn) -- 1: 1watt v1 (square) -- 2: 1watt v2 (inline)

  // Oled
  oled2_init();
  oled2_status("hello");

  // Wifi
  myIP += String(settings_get("id")+100);
  wifi_static(myIP);
  wifi_connect("24watt");
  wifi_ota( "watt-remote v" + String(CR_VERSION, 2) );
  wifi_onConnect(doOnConnect);
  wifi_onDisconnect(doOnDisconnect);

  // HTTP client
  http_init();

  // INPUTS
  pins = pinout[settings_get("model")];

  // SET PULLUP
  for(int k=0; k<5; k++) pinMode(pins[k], INPUT_PULLUP);
  
  // media1 
  attachInterrupt(digitalPinToInterrupt(pins[0]), []() {
    event_trigger(pins[0], media1);
  }, FALLING);

  // media2
  attachInterrupt(digitalPinToInterrupt(pins[1]), []() {
    event_trigger(pins[1], media2);
  }, FALLING);

  // media3
  attachInterrupt(digitalPinToInterrupt(pins[2]), []() {
    event_trigger(pins[2], media3);
  }, FALLING);

  // media4 
  attachInterrupt(digitalPinToInterrupt(pins[3]), []() {
    event_trigger(pins[3], media4);
  }, FALLING);

  // PUSH EN
  attachInterrupt(digitalPinToInterrupt(pins[4]), []() {
    event_trigger(pins[4], push);
  }, FALLING);

  // ENCODER
#ifdef DEBUG
#else
  encoder_init(RX, TX);
  encoder_inc( incr );
  encoder_dec( decr );
#endif

  //UDP
  // input socket
  udp_in.begin(hostPORT_osc);
}

void loop(void) {
  encoder_loop();
  event_loop();

  if (wifi_isok()) {
    wifi_otaCheck();

    if (udp_in.parsePacket()) {
      int len = udp_in.read(udpPacket, 1470);
      if (len >= 0) {
        udpPacket[len] = 0;
        //LOGF("UDP: packet received: %s\n", udpPacket);
        if (udpPacket[0] != '/') {
          oled2_status( getValue(udpPacket, '#', 0), getValue(udpPacket, '#', 1) );
          lastInfo = millis();
          lastNews = millis();
        }
      }
    }

    if (millis() - lastInfo > 200) {
      // STATUS check
      //LOG("sending synctest");
      udp_out.beginPacket(hostIP.c_str(), hostPORT_osc);
      OSCMessage msg("/synctest");
      msg.send(udp_out);
      udp_out.endPacket();
      lastInfo = millis() - 50;
    }

    if (millis() - lastNews > 1500) {
      oled2_status("-no rpi");
    }
  }
  else {
    oled2_status("+no wifi");
  }
  delay(50);

  if (SLEEPTIME > 0)
    if (millis() - lastNews > (SLEEPTIME * 60 * 1000))
      shutdown();
    
  //LOG("loop");
  oled2_loop();
}


/*
   on Connect
*/
void doOnConnect() {
  oled2_status("-wifi ok");
}

/*
   on Disconnect
*/
void doOnDisconnect() {
  if (!shuttingDown) oled2_status("-no wifi");
}

void media1() {
  http_get("/event/btn1");
}

void media2() {
  http_get("/event/btn2");
}

void media3() {
  http_get("/event/btn3");
}

void media4() {
  http_get("/event/btn4");
}

void incr() {
  http_get("/event/inc");
}

void decr() {
  http_get("/event/dec");
}

void push() {
  http_get("/event/push");
}

void shutdown() {
  shuttingDown = true;
  wifi_disarm();
  //oled2_status("          ", "          ");
  oled2_clear();
  WiFi.mode(WIFI_OFF);
  ESP.wdtDisable();
  ESP.deepSleep(0);
}
