from .base import BaseInterface
import time
import threading
import platform
from typing import Optional

try:
    import rtmidi
except ImportError:  # pragma: no cover - optional dependency
    rtmidi = None

class MidictrlInterface(BaseInterface):
    
    def __init__(self, hplayer, device_filter="LPD8", retry=0):
        super().__init__(hplayer, "MidiCtrl")
        if rtmidi is None:
            raise RuntimeError("python-rtmidi module not available; MIDI interface disabled")

        self.device_filter = device_filter
        self._rtapi = self._select_api()
        try:
            self.midiin = rtmidi.MidiIn(rtapi=self._rtapi)
        except RuntimeError as exc:
            raise RuntimeError(f"MIDI backend unavailable: {exc}") from exc
        self._connection_attempts = 0
        self._max_retries = retry
        self._running = False
        self._callback_lock = threading.Lock()

    def _select_api(self):
        compiled = list(rtmidi.get_compiled_api())
        if not compiled:
            raise RuntimeError("No MIDI backend available")

        system = platform.system().lower()

        preference: list[Optional[int]] = []
        if system == "linux":
            preference.extend([
                getattr(rtmidi, "API_LINUX_ALSA", None),
                getattr(rtmidi, "API_UNIX_JACK", None),
            ])
        elif system == "darwin":
            preference.append(getattr(rtmidi, "API_MACOSX_CORE", None))
        elif system.startswith("win"):
            preference.append(getattr(rtmidi, "API_WINDOWS_MM", None))

        preference.append(getattr(rtmidi, "API_UNSPECIFIED", None))

        for api in preference:
            if api in compiled:
                return api

        return compiled[0]

    def _midi_callback(self, message_data, _):
        msg, _ = message_data
        with self._callback_lock:
            try:
                status = msg[0]
                msg_type = status & 0xF0
                channel = (status & 0x0F) + 1

                if msg_type == 0x90 and msg[2] > 0:  # Note On
                    handler_msg = {
                        'type': 'noteon',
                        'channel': channel,
                        'note': msg[1],
                        'velocity': msg[2]
                    }
                elif msg_type == 0x80 or (msg_type == 0x90 and msg[2] == 0):  # Note Off
                    handler_msg = {
                        'type': 'noteoff',
                        'channel': channel,
                        'note': msg[1],
                        'velocity': msg[2]
                    }
                elif msg_type == 0xB0:  # Control Change
                    handler_msg = {
                        'type': 'cc',
                        'channel': channel,
                        'control': msg[1],
                        'value': msg[2]
                    }
                elif msg_type == 0xC0:  # Program Change
                    handler_msg = {
                        'type': 'pc',
                        'channel': channel,
                        'program': msg[1]
                    }
                else:
                    return
                
                # self.log(f"Received MIDI message: {handler_msg}")

                self.emit(handler_msg['type'], handler_msg)

            except IndexError:
                self.log.error("Invalid MIDI message received")

    def _connection_manager(self):
        while self._running:
            
            # Check if the device is still available
            if self.midiin.is_port_open():
                device_found = False
                for i in range(self.midiin.get_port_count()):
                    name = self.midiin.get_port_name(i)
                    if self.device_filter in name:
                        device_found = True
                        break

                if not device_found:
                    self.log("MIDI device disconnected")
                    self.midiin.cancel_callback()
                    self.midiin.close_port()
                    
            # print("Checking MIDI connection...", self.midiin.is_port_open())
            
            doretry = not self.midiin.is_port_open()
            if self._max_retries > 0:
                doretry = doretry and self._connection_attempts < self._max_retries
                
            if doretry:
                try:
                    port_id = self._find_device()
                    if port_id is not None:
                        self.midiin.open_port(port_id)
                        self.log("MIDI connected successfully")
                        self.emit('ready')
                        self._connection_attempts = 0
                        self.midiin.set_callback(self._midi_callback)
                    else:
                        raise RuntimeError("Device not found")

                except (RuntimeError, Exception) as e:
                    self._connection_attempts += 1
                    retry_delay = min(2 ** self._connection_attempts, 30)
                    self.log(f"Connection failed: {str(e)}. Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
            else:
                time.sleep(1)

    def _find_device(self):
        self.log("Available MIDI devices:")
        for i in range(self.midiin.get_port_count()):
            name = self.midiin.get_port_name(i)
            self.log(f" - {name}")
            if self.device_filter in name:
                return i
        return None
    
    def listen(self):
        self.log("starting MidiCtrl listener")
        self.stopped.wait()
        self.log("MidiCtrl listener stopped")
        if self.midiin.is_port_open():
            self.midiin.cancel_callback()
            self.midiin.close_port()

    def start(self):
        if not self._running:
            self._running = True
            super().start()
            self.conn_thread = threading.Thread(target=self._connection_manager, daemon=True)
            self.conn_thread.start()
            self.log("MIDI interface started")

    def quit(self, join=True):
        if self._running:
            self._running = False
            if self.midiin.is_port_open():
                self.midiin.cancel_callback()
                self.midiin.close_port()
            super().quit(join)
            self.conn_thread.join()