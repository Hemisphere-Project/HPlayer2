/*
   SETTINGS
*/
//#define DEV_ID 13

#define CR_VERSION  0.01  // Init
#define CR_VERSION  0.02  // 1watt teleco
#define CR_VERSION  0.03  // 1watt teleco
#define CR_VERSION  0.04  // settings EEPROM
#define CR_VERSION  0.05  // TTGO version 2020
#define CR_VERSION  0.06  // M5Core version 2020

#define SLEEPTIME 2       // minutes before going to sleep

#include <Arduino.h>
#include <OSCMessage.h> //https://github.com/stahlnow/OSCLib-for-ESP8266
#include <M5Stack.h>
#include "debug.h"
#include "wifi.h"

#define KEYBOARD_I2C_ADDR     0X08
#define KEYBOARD_INT          5

bool shuttingDown = false;
bool DEBUG_BTNS = true;

//UDP
WiFiUDP udp_in;
WiFiUDP udp_out;
char udpPacket[1472];

long lastInfo = 0;
long lastNews = 0;
long lastBat = 0;

// IP
String myIP = "10.0.0.";
String myName = "Remote ";

String hostIP = "10.0.0.1";
int hostPORT_http = 8037;
int hostPORT_osc = 4000;

Button Btn1 = Button(2, true, DEBOUNCE_MS);
Button Btn2 = Button(19, true, DEBOUNCE_MS);
Button Btn3 = Button(16, true, DEBOUNCE_MS);
Button Btn4 = Button(3,  true, DEBOUNCE_MS);

void setup(void) {

  // M5
  M5.begin(true, false, false, false);
  M5.Power.begin();
  M5.Speaker.mute();
  dacWrite(25,0);
  
  LOGSETUP();
  LOG("hello");
  
  // Settings config
  String keys[16] = {"id"};
  settings_load( keys );

  // Settings SET EEPROM !
  #ifdef DEV_ID
    settings_set("id", DEV_ID);
    LOGF("ID: %d\n", DEV_ID);
  #endif

  myName += String(settings_get("id")); 
  
  // M5 FACES
  Wire.begin();
  pinMode(KEYBOARD_INT, INPUT_PULLUP);

  // EXT BTNS
  pinMode(2, INPUT_PULLUP);
  pinMode(19, INPUT_PULLUP);
  pinMode(16, INPUT_PULLUP);
  pinMode(3, INPUT_PULLUP);
  digitalWrite(2, HIGH);
  digitalWrite(19, HIGH);
  digitalWrite(16, HIGH);
  digitalWrite(3, HIGH);

  // DISPLAY
  tft_init();

  // Wifi
  myIP += String(settings_get("id") + 100);
  wifi_static(myIP);
  wifi_connect("24watt");
  wifi_ota( "watt-remote v" + String(CR_VERSION, 2) );
  wifi_onConnect(doOnConnect);
  wifi_onDisconnect(doOnDisconnect);

  // HTTP client
  http_init();

  //UDP
  // input socket
  udp_in.begin(hostPORT_osc);
}

void loop(void)
{
  //LOGF4("btn: %d %d %d %d\n",  digitalRead(2),  digitalRead(19), digitalRead(16), digitalRead(3));
  M5.update();

  // A/B/C Buttons
  //
  if (M5.BtnA.wasPressed() || M5.BtnA.isPressed())
    event_trigger(0, []() {
    http_get("/event/dec");
    if (DEBUG_BTNS) tft_btns("down");
  });

  if (M5.BtnC.wasPressed() || M5.BtnC.isPressed())
    event_trigger(1, []() {
    http_get("/event/inc");
    if (DEBUG_BTNS) tft_btns("up");
  });

  if (M5.BtnB.wasPressed())
    event_trigger(2, []() {
    http_get("/event/push");
    if (DEBUG_BTNS) tft_btns("ok");
  });

  //Serial.printf("%d %d %d %d\n", digitalRead(2), digitalRead(19), digitalRead(16), digitalRead(3));

  // EXT BTNS
  Btn1.read();
  if (Btn1.wasPressed())
    event_trigger(3, []() {
    http_get("/event/btn1");
    if (DEBUG_BTNS) tft_btns("btn1");
  });

  Btn2.read();
  if (Btn2.wasPressed())
    event_trigger(4, []() {
    http_get("/event/btn2");
    if (DEBUG_BTNS) tft_btns("btn2");
  });

  Btn3.read();
  if (Btn3.wasPressed())
    event_trigger(5, []() {
    http_get("/event/btn3");
    if (DEBUG_BTNS) tft_btns("btn3");
  });

  Btn4.read();
  if (Btn4.wasPressed())
    event_trigger(6, []() {
    http_get("/event/btn4");
    if (DEBUG_BTNS) tft_btns("btn4");
  });

  // FACE
  //
  if (digitalRead(KEYBOARD_INT) == LOW) {
    Wire.requestFrom(KEYBOARD_I2C_ADDR, 1);  // request 1 byte from keyboard
    while (Wire.available()) {
      uint8_t key_val = Wire.read();                  // receive a byte as character

      switch ((char)key_val) {
        case '0': http_get("/event/KEY_KP0-down"); break;
        case '1': http_get("/event/KEY_KP1-down"); break;
        case '2': http_get("/event/KEY_KP2-down"); break;
        case '3': http_get("/event/KEY_KP3-down"); break;
        case '4': http_get("/event/KEY_KP4-down"); break;
        case '5': http_get("/event/KEY_KP5-down"); break;
        case '6': http_get("/event/KEY_KP6-down"); break;
        case '7': http_get("/event/KEY_KP7-down"); break;
        case '8': http_get("/event/KEY_KP8-down"); break;
        case '9': http_get("/event/KEY_KP9-down"); break;

        case '.': http_get("/event/KEY_KPDOT-down"); break;
        case '=': http_get("/event/KEY_KPENTER-down"); break;
        case '-': http_get("/event/KEY_KPMINUS-down"); break;
        case '+': http_get("/event/KEY_KPPLUS-down"); break;

        case 'A': http_get("/event/btn1"); break;
        case 'M': http_get("/event/btn2"); break;
        case '%': http_get("/event/btn3"); break;
        case '/': http_get("/event/btn4"); break;
      }
      tft_btns(String(key_val));
    }
  }

  event_loop();


  if (wifi_isok()) {
    wifi_otaCheck();

    if (DEBUG_BTNS) {
      DEBUG_BTNS = false;   // once connected, disable DEBUG_BTNS
      tft_btns("");
    }

    if (udp_in.parsePacket()) {
      int len = udp_in.read(udpPacket, 1470);
      if (len >= 0) {
        udpPacket[len] = 0;
        //LOGF("UDP: packet received: %s\n", udpPacket);
        if (udpPacket[0] != '/') {
          tft_status( getValue(udpPacket, '#', 0), getValue(udpPacket, '#', 1) );
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
      //LOG("sync");
    }

    if (millis() - lastNews > 1500) {
      tft_status(myName, "-no rpi");
    }
  }
  else {
    tft_status(myName, "+no wifi");
  }
  delay(50);

  if (SLEEPTIME > 0)
    if (millis() - lastNews > (SLEEPTIME * 60 * 1000))
      M5.Power.powerOFF();

  //LOG("loop");

  if (millis() - lastBat > 1000) {
    tft_mon();
    lastBat = millis();
  }

}


/*
   on Connect
*/
void doOnConnect() {
  tft_status("-wifi ok");
}

/*
   on Disconnect
*/
void doOnDisconnect() {
  if (!shuttingDown) tft_status("-no wifi");
}
