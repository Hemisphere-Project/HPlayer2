#include <ESP8266HTTPClient.h>

HTTPClient http;

void http_init() {
  http.setReuse(true);
}

/*
 * HTTP request 
 */
String http_get(String url) {
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
