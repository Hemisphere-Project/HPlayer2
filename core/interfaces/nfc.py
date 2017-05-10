from __future__ import print_function

from termcolor import colored
from time import sleep
import binascii
import sys

from base import BaseInterface


###
### ADAFRUIT NFC PN532
### https://github.com/adafruit/Adafruit_Python_PN532
###
import Adafruit_PN532 as PN532


class NfcInterface (BaseInterface):

    state = {}

    def __init__(self, player, args):

        if len(args) < 1:
            args[0] = 1000
            print(self.nameP, 'default timeout:', args[0] ,'ms')

        # Interface settings
        super(NfcInterface, self).__init__(player)
        self.name = "NFC "+player.name
        self.nameP = colored(self.name,'blue')

        # Timeout
        self.timeout = args[0]
        self.timeout_divider = 10
        self.timeout_internal = self.timeout*1.0 / self.timeout_divider
        if self.timeout_internal < 0.02:
            self.timeout_internal = 0.02
            self.timeout_divider = max(2, round(self.timeout / self.timeout_internal))

        # Internal data
        self.card = None

        # NFC config
        self.nfc = PN532.PN532(cs=18, sclk=25, mosi=23, miso=24)
        self.nfc.begin()

        # NFC info
        ic, ver, rev, support = self.nfc.get_firmware_version()
        print(self.nameP, 'Found PN532 with firmware version: {0}.{1}'.format(ver, rev))

        # NFC configure with MiFare cards.
        self.nfc.SAM_configuration()

        self.start()

    # NFC receiver THREAD
    def receive(self):
        print(self.nameP, "starting NFC listener")

        timeout_counter = -1;
        while self.isRunning():
            uid = self.nfc.read_passive_target(timeout_sec=self.timeout_internal)

            # Card detected
            if uid is not None:

                timeout_counter = self.timeout_divider          # Reset watcher

                # Extract card info
                read = {}
                read['uid'] = binascii.hexlify(uid)
                read['data'] = None

                # Check if card is new
                if self.card is None or self.card['uid'] != read['uid']:

                    # SAVE new card
                    self.card = read

                    # READ DATA
                    # Authenticate block 4 for reading with default key (0xFFFFFFFFFFFF).
                    if self.nfc.mifare_classic_authenticate_block(uid, 4, PN532.MIFARE_CMD_AUTH_B, [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]):
                        # Read block 4 data.
                        data = self.nfc.mifare_classic_read_block(4)
                        if data is not None:
                            self.card['data'] = binascii.hexlify(data[:4])
                            self.card['error'] = None
                        else:
                            self.card['error'] = 'Failed to read block 4!'
                    else:
                        self.card['error'] = 'Failed to authenticate block 4!'

                    # TRIGGER event
                    self.player.trigger('nfc-card', [self.card])


            # No Card detected
            elif timeout_counter > 0:
                    timeout_counter -= 1

            # Reach end of timeout counter: trigger event nocard
            if timeout_counter == 1:
                self.card = None                    # Unregister card
                self.player.trigger('nfc-nocard')   # Trigger event


        self.isRunning(False)
        return
