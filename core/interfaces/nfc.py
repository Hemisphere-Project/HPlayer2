from .base import BaseInterface
from time import sleep
import binascii
import sys



###
### ADAFRUIT NFC PN532
### https://github.com/adafruit/Adafruit_Python_PN532
###
import Adafruit_PN532 as PN532


class NfcInterface (BaseInterface):

    state = {}

    def __init__(self, hplayer, timeout=1000, divider=5):

        self.log('timeout:', timeout ,'ms')
        self.log('divider:', divider ,'ms')

        # Interface settings
        super(NfcInterface, self).__init__(hplayer, "NFC")

        # Timeout
        self.timeout = timeout
        self.timeout_divider = divider
        self.timeout_internal = self.timeout*1.0 / self.timeout_divider
        if self.timeout_internal < 0.02:
            self.timeout_internal = 0.02
            self.timeout_divider = max(2, round(self.timeout / self.timeout_internal))

        # Internal data
        self.card = None

        # NFC config
        self.nfc = PN532.PN532(cs=18, sclk=25, mosi=23, miso=24)
        try:
            self.nfc.begin()
        except Exception as e:
            self.log('PN532 not found... exit !')
            self.stopped.set()
            return

        # NFC info
        ic, ver, rev, support = self.nfc.get_firmware_version()
        self.log('Found PN532 with firmware version: {0}.{1}'.format(ver, rev))

        # NFC configure with MiFare cards.
        self.nfc.SAM_configuration()


    # NFC listener THREAD
    def listen(self):
        self.log("starting NFC listener")

        timeout_counter = -1;
        while self.isRunning():
            uid = self.nfc.read_passive_target(timeout_sec=self.timeout_internal)
            # uid = self.nfc.read_passive_target()
            print(uid)

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
                    self.emit('card', [self.card])


            # No Card detected
            elif timeout_counter > 0:
                timeout_counter -= 1
                self.log("count", timeout_counter)

            # Reach end of timeout counter: trigger event nocard
            if timeout_counter == 1:
                self.card = None                    # Unregister card
                self.emit('nocard')   # Trigger event

            # if timeout_counter == -10:
            #     timeout_counter = 0
            #     self.nfc.begin()
            #     self.nfc.SAM_configuration()
