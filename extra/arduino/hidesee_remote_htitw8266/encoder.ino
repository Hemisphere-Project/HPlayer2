#include <EC11.hpp>  // http://github.com/aleh/ec11

EC11 encoder;
int encoderPinA;
int encoderPinB;

void (*_encoder_inc)();
void (*_encoder_dec)();

void ICACHE_RAM_ATTR _encoder_inter() {
  encoder.checkPins(digitalRead(encoderPinA), digitalRead(encoderPinB));
}

void encoder_init(int pinA, int pinB) {
  encoderPinA = pinA;
  encoderPinB = pinB;
  pinMode(encoderPinA, INPUT_PULLUP);
  pinMode(encoderPinB, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(encoderPinA), _encoder_inter, CHANGE);
  attachInterrupt(digitalPinToInterrupt(encoderPinB), _encoder_inter, CHANGE);
}

void encoder_loop() {
  EC11Event e;
  if (encoder.read(&e)) {
    if (e.type == EC11Event::StepCW) {
      _encoder_inc();
    } else {
      _encoder_dec();
    }
  }
}

void encoder_inc(void (*f)()) {
  event_set(encoderPinA, f);
  _encoder_inc = [](){ event_trigger(encoderPinA); };
}

void encoder_dec(void (*f)()) {
  event_set(encoderPinB, f);
  _encoder_dec = [](){ event_trigger(encoderPinB); };
}
