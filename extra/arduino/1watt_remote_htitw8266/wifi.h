#include <ESP8266WiFi.h>
#include <ESP8266mDNS.h>
#include <WiFiUdp.h>
#include <ArduinoOTA.h>

void wifi_ota(String nameDevice);
void _wifi_otabegin();
void wifi_otaCheck();
void wifi_static(String ip, String gateway, String mask);
void wifi_static(String ip, String gateway);
void wifi_static(String ip);
void wifi_connect(const char* ssid, const char* password);
void wifi_connect(const char* ssid);
bool wifi_isok();
void wifi_onConnect(void (*f)());
void _wifi_connected();
void wifi_onDisconnect(void (*f)());
void _wifi_disconnected();
void _wifi_event(WiFiEvent_t event);
bool wifi_wait(int timeout, bool restart);
bool wifi_wait(int timeout);


bool wifi_available = false;
byte wifi_retry = 0;
byte wifi_otaEnable = false;
String wifi_nameDevice = "esp32";
void (*wifi_conClbck)();
void (*wifi_disconClbck)();

bool disarming = false;

/*
 * Setup OTA
 */
void wifi_ota(String nameDevice) {
  wifi_otaEnable = true;
  wifi_nameDevice = nameDevice;
  ArduinoOTA.setHostname(nameDevice.c_str());
  _wifi_otabegin();
}
void _wifi_otabegin() {
  if (!wifi_otaEnable || !wifi_available) return;
  ArduinoOTA.begin();
  LOGINL("OTA: started = ");
  LOG(wifi_nameDevice);
}

/*
 * Wifi LOOP
 */
void wifi_otaCheck() {
  // Run OTA
  if (wifi_otaEnable && wifi_available) ArduinoOTA.handle();
}

/*
 * Setup static WIFI
 */
void wifi_static(String ip, String gateway, String mask) {
   IPAddress addrIP;
   addrIP.fromString(ip);
   IPAddress gateIP;
   if (gateway == "auto") {
    gateIP.fromString(ip);
    gateIP[3] = 1;
   }
   else gateIP.fromString(gateway);
   IPAddress maskIP;
   maskIP.fromString(mask);
   WiFi.config(addrIP, gateIP, maskIP);
}
void wifi_static(String ip, String gateway) {
   wifi_static(ip, gateway, "255.255.255.0");
}
void wifi_static(String ip) {
   wifi_static(ip, "auto");
}


/*
 * Connect as STATION
 */
void wifi_connect(const char* ssid, const char* password) {
  WiFi.mode(WIFI_OFF);
  delay(1);
  WiFi.mode(WIFI_STA);
  WiFi.onEvent(_wifi_event);
  WiFi.begin(ssid, password);
}
void wifi_connect(const char* ssid) {
  WiFi.mode(WIFI_OFF);
  delay(1);
  WiFi.mode(WIFI_STA);
  WiFi.onEvent(_wifi_event);
  WiFi.begin(ssid);
}

/*
 * Set Callback triggered when connection 
 * is (re-)established
 */
void wifi_onConnect(void (*f)()) {
  wifi_conClbck = f;
}

/*
 * Set Callback triggered when connection 
 * is (re-)established
 */
void wifi_onDisconnect(void (*f)()) {
  wifi_disconClbck = f;
}

/*
 * Get connection status
 */
bool wifi_isok() {
  return wifi_available;
}

/*
 * Internal callback
 */
void _wifi_connected() {
  _wifi_otabegin();
  (*wifi_conClbck)();
}

/*
 * Internal callback
 */
void _wifi_disconnected() {
  (*wifi_disconClbck)();
}

/*
 * Internal callback
 */
void _wifi_event(WiFiEvent_t event) {
  if (disarming) return;
  if (event == WIFI_EVENT_STAMODE_DISCONNECTED) {
    if (wifi_available) LOG("WIFI: disconnected");
    wifi_available = false;
    _wifi_disconnected();
    wifi_retry += 1;
    LOGF("WIFI: reconnecting.. %i\n", wifi_retry);
    WiFi.reconnect();
  }
  else if (event == WIFI_EVENT_STAMODE_GOT_IP) {
    wifi_retry = 0;
    if (wifi_available) return;
    wifi_available = true;   
    LOGINL("WIFI: connected = ");
    LOG(WiFi.localIP());
    _wifi_connected();
  }
}

/*
 * Wait for wifi to be connected, or until timeout
 * Can trigger Restart on timeout
 */
bool wifi_wait(int timeout, bool restart) {
  byte retries = 0;
  while(retries < timeout/100) {
    if (wifi_available) return true;
    retries += 1;
    delay(100);
  }
  if (restart) {
    LOG("\nWIFI: timeout is over, restarting..\n");
    ESP.restart();
  }
  else LOG("WIFI: timeout is over");
  return false;
}

bool wifi_wait(int timeout) {
  wifi_wait(timeout, false);
}

void wifi_disarm() {
  disarming = true;
}
