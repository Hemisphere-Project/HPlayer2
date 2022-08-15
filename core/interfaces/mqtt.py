from .base import BaseInterface
from ..engine import network
import paho.mqtt.client as mqtt
from time import sleep
from random import randrange

class MqttInterface (BaseInterface):

    def __init__(self, hplayer, _broker):
        super().__init__(hplayer, "MQTT")
        self.broker = _broker
        self.isConnected = False

    # The callback for when the client receives a CONNACK response from the server.
    def on_connect(self, client, userdata, flags, rc):
        self.log("Connected with broker at "+str(self.broker))
        self.isConnected = True

        devicename = network.get_hostname().lower()
        
        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        self.client.subscribe("rpi/all/#")
        self.client.subscribe("rpi/"+devicename+"/#")
        self.client.subscribe("rpi/random/#")


    def on_disconnect(self, client, userdata, msg):
        self.log("Disconnected from Broker")
        self.isConnected = False


    # The callback for when a PUBLISH message is received from the server.
    def on_message(self, client, userdata, msg):
        
        # Discard message randomly if dest is random based on zyre peer count
        if msg.topic.split('/')[1] == 'random':
            zyre = self.hplayer.interface('zyre')
            if zyre and zyre.activeCount() > 1 and randrange(zyre.activeCount()) > 0:
                return
                        
        event = '.'.join(msg.topic.split('/')[2:])
        self.emit(event, *list(msg.payload.decode().split('§')) )
    
    def send(self, topic, data=None, QOS=1):
        self.client.publish(topic, payload=data, qos=QOS, retain=False)
        if self.isConnected:
            self.log("send", topic, data)
        else:
            self.log("not connected.. can't send", topic, data)

    # MQTT loop
    def listen(self):

        self.log("starting MQTT client")

        self.client = mqtt.Client(client_id="", clean_session=True, userdata=None)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

        while True:
            try:
                self.client.connect(self.broker, port=1883, keepalive=30)
                break
            except:
                self.log("Can't connect to broker at ", self.broker, ", retrying...")
                for i in range(10):
                    sleep(0.5)
                    if not self.isRunning(): 
                        return

        self.client.loop_start()        
        self.stopped.wait()
        self.client.loop_stop(force=True)
