/*
   SETTINGS
*/
#define CR_VERSION  0.01  // Init

/*
   INCLUDES
*/
#include "debug.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include "SSD1306.h"
#include <OSCMessage.h> //https://github.com/stahlnow/OSCLib-for-ESP8266

HTTPClient http;

// TTGO
uint8_t ledPin = 16; // Onboard LED reference
SSD1306 display(0x3c, 5, 4); // instance for the OLED. Addr, SDA, SCL

// TOUCH
// www.areresearch.net/2018/01/how-to-use-ttgo-esp32-module-with-oled.html
// https://github.com/espressif/arduino-esp32/issues/112
int threshold = 40;
byte doNext = 0;
byte doStop = 0;

//UDP
WiFiUDP udp_in;
WiFiUDP udp_out;
char udpPacket[1472];

long lastInfo = 0;

/*
   SETUP
*/
void setup() {

  LOGSETUP();

  // Init Screen
  display.init(); // initialise the OLED
  //display.flipScreenVertically(); // does what is says
  dispStatus(":: disconnected ::");

  // Wifi
  wifi_static("3.0.0.10");
  //wifi_connect("interweb", "superspeed37");
  wifi_connect("ciconia");
  wifi_ota( "ciconia-remote v" + String(CR_VERSION, 2) );
  wifi_onConnect(doOnConnect);
  wifi_onDisconnect(doOnDisconnect);

  http.setReuse(true);

  // Touch
  touchAttachInterrupt(T2, touch2, threshold);  // Touch 2 = GPIO 2
  touchAttachInterrupt(T8, touch8, threshold);  // Touch 8 = GPIO 33

  LOG(HTTPCLIENT_DEFAULT_TCP_TIMEOUT);

  //UDP
  // input socket
  udp_in.begin(4001);
}

/*
   LOOP
*/
void loop() {
  if (wifi_isok()) {

    //LOG(touchRead(T2));

    // Commands
    if (doNext == 1) {
      httpGet("/next");
      doNext = 2;
    }
    if (doStop == 1) {
      httpGet("/stop");
      doStop = 2;
    }

    if (touchRead(T2) > threshold) doNext = 0;
    if (touchRead(T8) > threshold) doStop = 0;


    if (udp_in.parsePacket()) {
      //Serial.printf("Received %d bytes from %s, port %d\n", packetSize, Udp.remoteIP().toString().c_str(), Udp.remotePort());
      int len = udp_in.read(udpPacket, 1470);
      if (len >= 0) {
        udpPacket[len] = 0;
        //LOGF("UDP: packet received: %s\n", udpPacket);
        dispStatus( getValue(udpPacket, '/', 0), getValue(udpPacket, '/', 1) );
        lastInfo = millis();
      }
    }

    if (millis()-lastInfo > 200) {
      // STATUS check
      udp_out.beginPacket("3.0.0.1", 4000);
      OSCMessage msg("/synctest");
      msg.send(udp_out);
      udp_out.endPacket();
      lastInfo = millis()-50;
    }
    
    // MEDIA check
    /*String media = httpGet("/status/media");
    if (media == "None") media = "-stop-";
    else {
      media = media.substring(10);
      media = media.substring(0, media.length() - 1);
    }
    dispStatus(media);*/
    
  }
  else delay(100);
}

/*
 * TOUCH 2 (GPIO 2)
 */
void touch2() {
  if (doNext == 0) {
    LOG("TOUCH 2 (gpio 2)");
    doNext = 1;
  }
}

/*
 * TOUCH 8 (GPIO 33)
 */
void touch8() {
  if (doStop == 0) {
    LOG("TOUCH 8 (gpio 33)");
    doStop = 1;
  }
}


/*
   on Connect
*/
void doOnConnect() {
  dispStatus(":: connected ::");
  //httpGet("/loop");
  //httpGet("/play/earth.mp4");
}

/*
   on Disconnect
*/
void doOnDisconnect() {
  dispStatus(":: disconnected ::");
  //httpGet("/loop");
  //httpGet("/play/earth.mp4");
}

/*
 * HTTP request 
 */
String httpGet(String url) {
  if (!wifi_isok()) {
    LOG("httpGet CANCELLED: no wifi...");
    return "";
  }
  http.begin("http://3.0.0.1:8037" + url);
  int httpCode = http.GET();
  String payload = "";
  if (httpCode > 0) { //Check for the returning code
    payload = http.getString();
  } else {
    payload = "ERROR "+String(httpCode);
    LOG("Error on HTTP request: " + String(httpCode));
  }
  http.end();
  LOG(payload);
  return payload;
}

/*
 * Show status
 */
void dispStatus(String stat) {
  dispStatus(stat, "");
}

void dispStatus(String stat, String stat2) {
  display.setFont(ArialMT_Plain_16);
  display.setTextAlignment(TEXT_ALIGN_LEFT);
  display.clear();
  display.drawString(0, 0, "Ciconia");
  display.drawString(10, 24, stat);
  display.drawString(10, 48, stat2);
  display.display();
}

/*
 * Split String
 */

String getValue(String data, char separator, int index)
{
  int found = 0;
  int strIndex[] = {0, -1};
  int maxIndex = data.length()-1;

  for(int i=0; i<=maxIndex && found<=index; i++){
    if(data.charAt(i)==separator || i==maxIndex){
        found++;
        strIndex[0] = strIndex[1]+1;
        strIndex[1] = (i == maxIndex) ? i+1 : i;
    }
  }

  return found>index ? data.substring(strIndex[0], strIndex[1]) : "";
}
