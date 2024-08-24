#include <Arduino.h>
#include <M5Stack.h>
#include "Unit_4RELAY.h"

UNIT_4RELAY relay;

// inputs on Base PortB et PortC
#define IN1_PIN 26 // or 36
#define IN2_PIN 17 // or 16

int state = LOW;
int state1 = LOW;
int state2 = LOW;

unsigned long lowEngaged = 0;
const int debounceDelay = 2000;

int relayState = 0;

void setup() 
{
  M5.begin(false, false, true, true); 
  delay(100);

  pinMode(IN1_PIN, INPUT_PULLUP);
  pinMode(IN2_PIN, INPUT_PULLUP);

  relay.begin();
  relay.Init(0); 
  relay.relayWrite(0, 1);
  relayState = 1;

  Serial.println("/prox READY");
}

void loop() 
{
  M5.update();
  
  // BTNA forced trigger
  if (M5.BtnA.wasPressed()) {
    Serial.println("/prox ON");
  }
  // BTNB forced trigger
  if (M5.BtnB.wasPressed()) {
    Serial.println("/prox OFF");
  }
  // BTNC forced trigger
  if (M5.BtnC.wasPressed()) {
    if (relayState == 0) {
      relay.relayWrite(0, 1);
      relayState = 1;
      Serial.println("RELAY ON");
    } else {
      relay.relayWrite(0, 0);
      relayState = 0;
      Serial.println("RELAY OFF");
    }
  }

  

  // IN1 trigger
  int s1 = !digitalRead(IN1_PIN);
  if (s1 != state1) {
    // if (s1 == HIGH) Serial.println("IN1 ON");
    // else            Serial.println("IN1 OFF");
    state1 = s1;
  }

  // IN2 trigger
  int s2 = !digitalRead(IN2_PIN);
  if (s2 != state2) {
    // if (s2 == HIGH) Serial.println("IN2 ON");
    // else            Serial.println("IN2 OFF");
    state2 = s2;
  }

  // Global state with debounce
  int s = state1 || state2;

  if (s) lowEngaged = 0;
  else if (lowEngaged == 0) lowEngaged = millis();

  if (s != state) {
    if (millis() - lowEngaged > debounceDelay) {
      state = s;
      if (state == HIGH)  Serial.println("/prox ON");
      else                Serial.println("/prox OFF");
    }
  }

  // Read serial and look for /relay/1
  if (Serial.available()) {
    String str = Serial.readStringUntil('\n');
    if (str == "/relay/1") {
      relay.relayWrite(0, 1);
      relayState = 1;
      Serial.println("RELAY ON");
    }
    if (str == "/relay/0") {
      relay.relayWrite(0, 0);
      relayState = 0;
      Serial.println("RELAY OFF");
    }
  }

  delay(1);
}