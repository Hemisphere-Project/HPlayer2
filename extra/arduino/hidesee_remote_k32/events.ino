#define DEBOUNCE_TIME 300
#define EVENTS_MAX 64

long event_last[EVENTS_MAX];
bool event_state[EVENTS_MAX];
void (*event_fn[EVENTS_MAX])();

bool event_debounce(int ev) {
  if( ev >= EVENTS_MAX ) return false;
  if ((millis()-event_last[ev]) < DEBOUNCE_TIME) {
    //LOG("debounced");
    return false;
  }
  event_last[ev] = millis();
  //LOG("triggered");
  return true;
}

void event_trigger(int ev) {
  if( event_debounce(ev) ) event_state[ev] = true;
}

void event_trigger(int ev, void (*clbck)()) {
  event_set(ev, clbck);
  event_trigger(ev);
}

void event_set(int ev, void (*clbck)()) {
  if( ev < EVENTS_MAX ) event_fn[ev] = clbck;
}

void event_loop() {
  for(int ev=0; ev<EVENTS_MAX; ev++) 
    if (event_state[ev]) {
      event_state[ev] = false;
      event_fn[ev]();
    }
}
