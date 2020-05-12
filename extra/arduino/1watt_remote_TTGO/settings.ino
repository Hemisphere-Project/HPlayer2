#include <EEPROM.h>

String settings_keys[16];
byte settings_values[16];

void settings_add(byte k, String key) {
  settings_keys[k] = key;
}

void settings_load(String keys[16]) {
  for (byte k=0; k<16; k++) settings_keys[k] = keys[k];
  EEPROM.begin(16);
  for (byte k=0; k<16; k++) settings_values[k] = EEPROM.read(k);
  EEPROM.end();  
}

void settings_set(String key, byte value) {
  for (byte k=0; k<16; k++) 
    if (settings_keys[k] == key) {
      EEPROM.begin(16);
      EEPROM.write(k, value);
      EEPROM.end();
      settings_values[k] = value;
      return;
    }
}

byte settings_get(String key) {
  for (byte k=0; k<16; k++) 
    if (settings_keys[k] == key) {
      byte value = settings_values[k]; 
      return value;
    }
  return 0;
}
