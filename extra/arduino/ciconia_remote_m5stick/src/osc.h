#include <Arduino.h>
#include <OSCMessage.h> //https://github.com/stahlnow/OSCLib-for-ESP8266

//UDP
WiFiUDP udp_in;
WiFiUDP udp_out;
char udpPacket[1472];

int hostPORT_osc = 4000;
int remotePORT_osc = 4001;

void osc_init() {
    udp_in.begin(remotePORT_osc);
}