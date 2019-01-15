/*
   SETTINGS
*/
#define CR_VERSION  0.01  // Init
#define CR_VERSION  0.02  // 1watt teleco
#define CR_VERSION  0.03  // 1watt teleco
#define CR_VERSION  0.04  // settings EEPROM
#define CR_VERSION  0.05  // k32

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
String hostIP = "3.0.0.1"; //AP wifi
int hostPORT_http = 8037;
int hostPORT_osc = 4000;

// PINS
#define SPI_SCK 14
#define SPI_MISO 12
#define SPI_MOSI 13
#define SPI_CS 15
#define DMX_DE 4
#define DMX_DI 16
#define DMX_RO 17
#define I2S_LRCK 25
#define I2S_DATA 26
#define I2S_BCK 27
#define LED_DATA_1 23
#define LED_DATA_2 22
//

// Pinout: {dec, inc, push, btn1, btn2, btn3, btn4, btn5, btn6, btn7, btn8, btn9}
int pins[12] = {SPI_SCK, SPI_MISO, SPI_MOSI, SPI_CS, DMX_DE, DMX_DI, DMX_RO, I2S_LRCK, I2S_DATA, I2S_BCK, LED_DATA_1, LED_DATA_2};

void ICACHE_RAM_ATTR btnPush() {
  event_trigger(pins[2], [](){ 
    http_get("/event/push");
  });
}

void ICACHE_RAM_ATTR btn1() {
  event_trigger(pins[3], [](){ 
    http_get("/event/btn1");  
  });
}

void ICACHE_RAM_ATTR btn2() {
  event_trigger(pins[4], [](){ 
    http_get("/event/btn2");  
  });
}

void ICACHE_RAM_ATTR btn3() {
  event_trigger(pins[5], [](){ 
    http_get("/event/btn3");  
  });
}

void ICACHE_RAM_ATTR btn4() {
  event_trigger(pins[6], [](){ 
    http_get("/event/btn4");  
  });
}

void ICACHE_RAM_ATTR btn5() {
  event_trigger(pins[7], [](){ 
    http_get("/event/btn5");  
  });
}

void ICACHE_RAM_ATTR btn6() {
  event_trigger(pins[8], [](){ 
    http_get("/event/btn6");  
  });
}

void ICACHE_RAM_ATTR btn7() {
  event_trigger(pins[9], [](){ 
    http_get("/event/btn7");  
  });
}

void ICACHE_RAM_ATTR btn8() {
  event_trigger(pins[10], [](){ 
    http_get("/event/btn8");  
  });
}

void ICACHE_RAM_ATTR btn9() {
  event_trigger(pins[11], [](){ 
    http_get("/event/btn9");  
  });
}

void incr() {
  http_get("/event/inc");
}

void decr() {
  http_get("/event/dec");
}

void setup(void) {
  LOGSETUP();
  LOG("hello");

  // Settings config
  String keys[16] = {"id", "model"};
  settings_load( keys );

  // Settings SET EEPROM !
  settings_set("id", 5);
  settings_set("model", 3);   // 3: h&s

  // Oled
  oled2_init();
  oled2_status("hello");

  // Wifi
  wifi_connect("hsremote");
  wifi_ota( "hidesee-remote v" + String(CR_VERSION, 2) );
  wifi_onConnect(doOnConnect);
  wifi_onDisconnect(doOnDisconnect);

  // HTTP client
  http_init();

  // SET PULLUP
  for(int k=0; k<12; k++) pinMode(pins[k], INPUT_PULLUP);

  // media1 
  attachInterrupt(digitalPinToInterrupt(pins[2]), btnPush, FALLING);
  attachInterrupt(digitalPinToInterrupt(pins[3]), btn1, FALLING);
  attachInterrupt(digitalPinToInterrupt(pins[4]), btn2, FALLING);
  attachInterrupt(digitalPinToInterrupt(pins[5]), btn3, FALLING);
  attachInterrupt(digitalPinToInterrupt(pins[6]), btn4, FALLING);
  attachInterrupt(digitalPinToInterrupt(pins[7]), btn5, FALLING);
  attachInterrupt(digitalPinToInterrupt(pins[8]), btn6, FALLING);
  attachInterrupt(digitalPinToInterrupt(pins[9]), btn7, FALLING);
  attachInterrupt(digitalPinToInterrupt(pins[10]), btn8, FALLING);
  attachInterrupt(digitalPinToInterrupt(pins[11]), btn9, FALLING);


  // ENCODER
  encoder_init(pins[0], pins[1]);
  encoder_inc( incr );
  encoder_dec( decr );

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
      LOG("sync");
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


void shutdown() {
  shuttingDown = true;
  wifi_disarm();
  //oled2_status("          ", "          ");
  oled2_clear();
  WiFi.mode(WIFI_OFF);
  //ESP.wdtDisable();
  ESP.deepSleep(0);
}
