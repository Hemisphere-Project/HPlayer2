from .base import BaseInterface
import paho.mqtt.client as mqtt


class MqttInterface (BaseInterface):

    def __init__(self, hplayer, _broker):
        super().__init__(hplayer, "MQTT")
        self.broker = _broker


    # The callback for when the client receives a CONNACK response from the server.
    def on_connect(self, client, userdata, flags, rc):
        self.log("Connected with broker at "+str(self.broker))

        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        # self.client.subscribe("light/mem")


    # The callback for when a PUBLISH message is received from the server.
    def on_message(self, client, userdata, msg):
        self.log(msg.topic+" "+str(msg.payload.decode()))
    
    
    def send(self, topic, data=None):
        self.client.publish(topic, payload=data, qos=1, retain=False)
        self.log("send", topic, data)

    # GPIO receiver THREAD
    def listen(self):

        self.log("starting MQTT client")

        self.client = mqtt.Client(client_id="", clean_session=True, userdata=None)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        self.client.connect(self.broker, port=1883, keepalive=30)
        
        self.client.loop_start()
        self.stopped.wait()
        self.client.loop_stop(force=True)
