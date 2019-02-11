/*
   SETTINGS
*/
#define CR_VERSION  0.01  // Init
#define CR_VERSION  0.02  // 1watt teleco

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


void setup(void) {
  LOGSETUP();
  LOG("hello");

  // Oled
  oled_init();
  oled_status("hello");

  // Wifi
  //wifi_static("3.0.0.10");
  wifi_connect("hmspi");
  //wifi_connect("kxkm-wifi", "KOMPLEXKAPHARNAUM");
  wifi_ota( "hmspi-remote v" + String(CR_VERSION, 2) );
  wifi_onConnect(doOnConnect);
  wifi_onDisconnect(doOnDisconnect);

  http_init();

  // D3 : BLUE
  pinMode(D3, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(D3), [](){ event_trigger(D3, media1); }, FALLING);

  // D7: GREEN
  pinMode(D7, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(D7), [](){ event_trigger(D7, media2); }, FALLING);

  // D6: YELLOW
  pinMode(D6, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(D6), [](){ event_trigger(D6, media3); }, FALLING);

  // SCL: RED
  pinMode(14, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(14), [](){ event_trigger(14, media4); }, FALLING);

  // SDA: PUSH ENC   ----  OK
  pinMode(2, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(2), [](){ event_trigger(2, stop); }, FALLING);

  // ENCODER
  encoder_init(3, 1);
  encoder_inc( next );
  encoder_dec( prev );

  //UDP
  // input socket
  udp_in.begin(4001);
}

void loop(void) {
  encoder_loop();
  event_loop();

  if (wifi_isok()) {
    wifi_otaCheck();

    if (udp_in.parsePacket()) {
      //Serial.printf("Received %d bytes from %s, port %d\n", packetSize, Udp.remoteIP().toString().c_str(), Udp.remotePort());
      int len = udp_in.read(udpPacket, 1470);
      if (len >= 0) {
        udpPacket[len] = 0;
        LOGF("UDP: packet received: %s\n", udpPacket);
        oled_status( getValue(udpPacket, '"', 0), "    "+getValue(udpPacket, '"', 1) );
        lastInfo = millis();
        lastNews = millis();
      }
    }

    if (millis()-lastInfo > 200) {
      // STATUS check
      LOG("sending synctest");
      udp_out.beginPacket("3.0.0.1", 4000);
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
    oled_status("+no wifi");
  }
  delay(50);

  if (millis()-lastNews > (SLEEPTIME*60*1000)) {
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

void media1() {
  http_get("/play/1");
  oled_clear2();
}

void media2() {
  http_get("/play/2");
  oled_clear2();
}

void media3() {
  http_get("/play/3");
  oled_clear2();
}

void media4() {
  http_get("/play/4");
  oled_clear2();
}

void next() {
  http_get("/next");
  oled_clear2();
}

void prev() {
  http_get("/prev");
  oled_clear2();
}

void stop() {
  http_get("/stop");
  oled_clear2();
}

void test() {
  oled_status("test");
}

void shutdown() {
  shuttingDown = true;
  wifi_disarm();
  oled_status("          ","          ");
  WiFi.mode(WIFI_OFF);
  ESP.wdtDisable();
  ESP.deepSleep(0);
}
