#include <HTTPClient.h>

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
  LOG(url);
  if (!wifi_isok()) {
    LOG("request CANCELLED: no wifi...");
    return "";
  }
  http.begin( http_path + url);
  int httpCode = http.GET();
  String payload = "";
  if (httpCode > 0) { //Check for the returning code
    //payload = http.getString();   // VERY SLOW TO GET PAYLOAD !! 
  } else {
    payload = "ERROR "+String(httpCode);
    LOG("Error on HTTP request: " + String(httpCode));
  }
  http.end();
  return payload;
}
