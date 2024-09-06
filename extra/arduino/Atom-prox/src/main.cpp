#include <Arduino.h>
#include "M5Atom.h"

#define PIR_PIN 26

uint8_t ledBuf[3];

int state;


void ledState(int s)
{
  if (s == LOW) M5.dis.fillpix({255, 0, 0});
  else M5.dis.fillpix({0, 255, 0});
}

void setup() 
{
  M5.begin(true, false, true); 
  delay(100);
  pinMode(PIR_PIN, INPUT);

  Serial.println("prox READY");
  
  state = LOW;
  ledState(state);
  Serial.println("prox ON");
}

void loop() 
{
  M5.update();
  
  // BTN forced trigger
  if (M5.Btn.wasPressed()) {
    Serial.println("prox ON");
    state = LOW;
    ledState(state);
    delay(1000);
  }

  // PIR trigger
  int s = digitalRead(PIR_PIN);
  if (s != state) {
    if (s == LOW) Serial.println("prox ON");
    else          Serial.println("prox OFF");
    state = s;
    ledState(state);
  }
  else delay(1);

}