#include <ESP8266HTTPClient.h>

HTTPClient http;

String http_path;

void http_init() {
  http.setReuse(true);
  http_path = "http://"+hostIP+":"+String(hostPORT_http);
}

/*
 * HTTP request 
 */
String http_get(String url) {
  if (!wifi_isok()) {
    LOG("httpGet CANCELLED: no wifi...");
    return "";
  }
  http.begin( http_path + url);
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
