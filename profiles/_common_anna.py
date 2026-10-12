from core.engine import network

import os
from threading import Timer

# Shared by profiles/anna.py (Zyre parc) and profiles/25-annatv.py (nowde).
# The two stay independent profiles — one sync model each, pinned by the SD card's
# hplayer2@<profil> instance — and only the keypad LCD status screen lives here.
# The leading underscore says it is not a profile.

scrollSpeed = 3.08
introDuration = 1.5
blinkSpeed = 10


# Keypad LCD status screen
#   line 0: play/stop + playlist position + scrolling media name
#   line 1: volume + wifi, then suffix() if given (anna: Zyre peers)
#   overlay() returns a full screen that pre-empts the status (anna: keylock), or None
#   holdCounter > 10 (the profile counts select-hold) → hardreset
#
class StatusLCD:

	def __init__(self, hplayer, player, keypad, overlay=None, suffix=None):
		self.hplayer = hplayer
		self.player = player
		self.keypad = keypad
		self.overlay = overlay
		self.suffix = suffix
		self.holdCounter = 0
		self.blinkCounter = 0

	def update(self):
		keypad = self.keypad
		hplayer = self.hplayer
		player = self.player

		if self.holdCounter > 10:
			self.holdCounter = -1
			Timer(0.4, lambda: keypad.emit('hardreset')).start()

		if self.holdCounter < 0:
			keypad.lcd.set_color( 100, 0 , 0)
			return [".:: HPlayer2 ::.", "   restarting   "]

		if self.overlay:
			screen = self.overlay()
			if screen: return screen

		lines = ["", ""]

		media = player.status()['media']

		# Line 0 : MEDIA
		playlistCount = str(hplayer.playlist.index()+1) + "/" + str(hplayer.playlist.size())
		if media:
			lines[0] = keypad.CHAR_PLAY + playlistCount + " "

			media = os.path.basename(media)[:-4]
			skroller3 = max(0, (player.position()*scrollSpeed) % len(media) - introDuration * scrollSpeed)
			offset = min( int(skroller3), len(media)-15 +len(lines[0]) )
			lines[0] += media[offset:]

		else:
			lines[0] = keypad.CHAR_STOP + playlistCount

		lines[0] = lines[0].ljust(16, ' ')[:16]


		# Line 1 : VOLUME
		lines[1] = keypad.CHAR_VOL +str(hplayer.settings.get('volume')).ljust(5, ' ')

		# Line 1 : WIFI
		lines[1] += keypad.CHAR_WIFI
		if network.get_essid('wlan0'):
			lines[1] += (str( min(100, network.get_rssi('wlan0')) )+"%").ljust(6, ' ')
			self.blinkCounter = 1
		else:
			lines[1] += "---% "
			self.blinkCounter = (self.blinkCounter+1) % blinkSpeed

		if self.suffix:
			lines[1] += self.suffix()

		# COLORS
		if self.blinkCounter > 0: color = ( 100 if not media else 0 , 100, 100 if not media else 0)	# RED/GREEN: play state
		else: color = ( 0, 0 , 100)																	# BLUE flash: no wifi

		keypad.lcd.set_color( *color )

		return lines
