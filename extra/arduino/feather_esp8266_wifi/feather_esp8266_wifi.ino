/*
 *  Simple HTTP get webclient test
 */
 
#include <ESP8266WiFi.h>
 
const char* ssid     = "interweb";
const char* password = "superspeed37";
 
const char* host = "192.168.0.39";
const int httpPort = 8080;

const int pin1 = 12;
const int pin2 = 13;
const int pin3 = 14;

bool pushed1 = false;
bool pushed2 = false;
bool pushed3 = false;

WiFiClient client;

 
void setup() {
  Serial.begin(115200);
  delay(100);

  pinMode(pin1,INPUT_PULLUP);
  pinMode(pin2,INPUT_PULLUP);
  pinMode(pin3,INPUT_PULLUP);
  
}
  
void loop() {

  if (!connectWifi()) return;
  
  if (digitalRead(pin1) == LOW) {
    if (!pushed1) {
      pushed1 = true;
      sendPush(1);
    }
  }
  else pushed1 = false;

  if (digitalRead(pin2) == LOW) {
    if (!pushed2) {
      pushed2 = true;
      sendPush(2);
    }
  }
  else pushed2 = false;

  if (digitalRead(pin3) == LOW) {
    if (!pushed3) {
      pushed3 = true;
      sendPush(3);
    }
  }
  else pushed3 = false;
  
}

bool connectWifi() {

  if (WiFi.status() == WL_CONNECTED) return true;
  
  Serial.println();
  Serial.println();
  Serial.print("Connecting to "+String(ssid)+" ");
  
  int count = 0;
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED && count < 40) {
    delay(500);
    count++;
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("!");
    Serial.print("WiFi connected, IP: "); 
    Serial.println(WiFi.localIP()); 
    return true;
  }
  else {
    Serial.println("X");
    Serial.print("Can't connect to WIFI"); 
    return false;
  }
  
  
}

void sendPush(int btn) {

  /*Serial.print("connecting to ");
  Serial.println(host);*/

  // Use WiFiClient class to create TCP connections
  if (!client.connect(host, httpPort)) {
    Serial.println("connection failed to "+String(host)+":"+String(httpPort));
    return;
  }
  
  // We now create a URI for the request
  String url = "/event/push"+String(btn);
  Serial.println(url);
  
  // This will send the request to the server
  client.print(String("GET ") + url + " HTTP/1.1\r\n" +
               "Host: " + host + "\r\n" + 
               "Connection: close\r\n\r\n");

  // Debounce
  delay(100);

  /*
  // Read all the lines of the reply from server and print them to Serial
  while(client.available()){
    String line = client.readStringUntil('\r');
    Serial.print(line);
  }
  
  Serial.println();
  Serial.println("closing connection");
  */

}

