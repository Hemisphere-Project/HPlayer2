from .base import BaseInterface
import paho.mqtt.client as mqtt
from time import sleep

class MqttInterface (BaseInterface):

    def __init__(self, hplayer, _broker):
        super().__init__(hplayer, "MQTT")
        self.broker = _broker
        self.isConnected = False

    # The callback for when the client receives a CONNACK response from the server.
    def on_connect(self, client, userdata, flags, rc):
        self.log("Connected with broker at "+str(self.broker))
        self.isConnected = True

        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        # self.client.subscribe("light/mem")


    def on_disconnect(self, client, userdata, msg):
        self.log("Disconnected from Broker")
        self.isConnected = False


    # The callback for when a PUBLISH message is received from the server.
    def on_message(self, client, userdata, msg):
        self.log(msg.topic+" "+str(msg.payload.decode()))
    
    
    def send(self, topic, data=None):
        self.client.publish(topic, payload=data, qos=1, retain=False)
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

        while self.isRunning():
            try:
                self.client.connect(self.broker, port=1883, keepalive=30)
                break
            except:
                self.log("Can't connect to broker at ", self.broker, ", retrying...")
                sleep(5)    

        self.client.loop_start()        
        self.stopped.wait()
        self.client.loop_stop(force=True)
