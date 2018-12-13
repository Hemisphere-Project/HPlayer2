/*
   SETTINGS
*/
#define CR_VERSION  0.01  // Init

#include <Arduino.h>
#include <OSCMessage.h> //https://github.com/stahlnow/OSCLib-for-ESP8266
#include "debug.h"
#include "wifi.h"

bool ready1 = false;
long doNext = 0;
long doStop = 0;



//UDP
WiFiUDP udp_in;
WiFiUDP udp_out;
char udpPacket[1472];

long lastInfo = 0;
long lastNews = 0;

//BTN
const byte interruptPin = 22;


void setup(void) {
  LOGSETUP();
  
  // Oled
  oled_init();
  oled_status("hello");

  // Wifi
  //wifi_static("3.0.0.10");
  //wifi_connect("ciconia");
  wifi_connect("interweb", "superspeed37");
  wifi_ota( "ciconia-remote v" + String(CR_VERSION, 2) );
  wifi_onConnect(doOnConnect);
  wifi_onDisconnect(doOnDisconnect);

  http_init();

  // Btn
  pinMode(interruptPin, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(interruptPin), next, FALLING);

  //UDP
  // input socket
  udp_in.begin(4001);
}

void loop(void) {
  if (wifi_isok()) {
    wifi_otaCheck();
    
    ready1 = true;
    
    // Commands
    if (doNext == 1) {
      http_get("/next");
      doNext = millis()+200;
    }
    if (doStop == 1) {
      http_get("/stop");
      doStop = millis()+200;
    }

    if (doNext >= 10 && doNext < millis()) doNext = 2;
    if (doStop >= 10 && doStop < millis()) doStop = 2;
    
    if (doNext == 2) doNext = 0;
    if (doStop == 2) doStop = 0;

    if (udp_in.parsePacket()) {
      //Serial.printf("Received %d bytes from %s, port %d\n", packetSize, Udp.remoteIP().toString().c_str(), Udp.remotePort());
      int len = udp_in.read(udpPacket, 1470);
      if (len >= 0) {
        udpPacket[len] = 0;
        LOGF("UDP: packet received: %s\n", udpPacket);
        oled_status( getValue(udpPacket, '/', 0), getValue(udpPacket, '/', 1) );
        lastInfo = millis();
        lastNews = millis();
      }
    }
    
    if (millis()-lastInfo > 200) {
      // STATUS check
      LOG("sending synctest");
      udp_out.beginPacket("3.0.0.1", 4000);
      //udp_out.beginPacket("192.168.0.26", 4000);
      OSCMessage msg("/synctest");
      msg.send(udp_out);
      udp_out.endPacket();
      lastInfo = millis()-50;
    }

    if (millis()-lastNews > 1500) {
      oled_status("-no rpi");
    }
  }
  else {
    oled_status("-no wifi");
  }
  delay(50);
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
  oled_status("-no wifi");
}

/*
 * TOUCH 2 (GPIO 2)
 */
void next() {
  if (ready1 && doNext == 0) {
    LOG("TOUCH 2 (gpio 2)");
    doNext = 1;
  }
}

/*
 * TOUCH 8 (GPIO 33)
 */
void stop() {
  if (ready1 && doStop == 0) {
    LOG("TOUCH 8 (gpio 33)");
    doStop = 1;
  }
}
