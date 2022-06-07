bool shuttingDown = false;

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

void next() {
  http_get("/next");
}

void prev() {
  http_get("/prev");
}

void stop() {
  http_get("/stop");
}

void shutdown() {
  shuttingDown = true;
  M5.Axp.PowerOff();
}