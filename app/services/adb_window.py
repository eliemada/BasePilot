"""Android capture behind the same interface used by the vision/bot code."""
import os

from app.services.adb_client import AdbClient, AdbError
from app.services.window_models import DescendantInfo, WindowCandidate
from app.utils.logger import setup_logger
from app.utils.window_settings_store import load_window_selection

logger = setup_logger('AdbWindow')
GAME_PACKAGE = 'com.supercell.clashofclans'


class AdbWindowService:
    def __init__(self, window_name='Clash of Clans', child_class='', *, client=None, serial=None):
        self.client = client or AdbClient()
        self.requested_serial = serial
        self.hwnd = 0  # Compatibility: the Android serial is the capture handle.
        self._size = None
        self.last_error = ''

    def _requested(self):
        saved = load_window_selection()
        return (self.requested_serial or os.environ.get('BASEPILOT_ADB_SERIAL') or
                (saved.title if saved.top_class == 'ADB' else None) or self.client.serial)

    def find_window(self):
        self.hwnd = 0
        self._size = None
        try:
            self.client.select(self._requested())
            self.require_game()
            self.hwnd = self.client.serial
            self.last_error = ''
            return True
        except AdbError as exc:
            self.last_error = str(exc)
            logger.warning('%s', exc)
            return False

    def require_game(self):
        package = self.client.foreground_package()
        if package != GAME_PACKAGE:
            raise AdbError(f'Open Clash of Clans on {self.client.serial}; foreground app is {package or "unknown"}.')

    def enumerate_windows(self):
        return [WindowCandidate(top_hwnd=d.serial, title=d.serial, top_class='ADB',
                                child_hwnd=d.serial if d.state == 'device' else 0,
                                child_class=f'Android ({d.state})') for d in self.client.devices()]

    def window_pixel_size(self, hwnd):
        # Picker diagnostics may inspect a different device without changing the
        # bot's selected transport or issuing any input.
        client = AdbClient(serial=hwnd, executable=self.client.executable)
        try:
            frame = client.capture()
            return frame.shape[1], frame.shape[0]
        except AdbError as exc:
            self.last_error = str(exc)
            return None

    def enumerate_descendants(self, root_hwnd):
        size = self.window_pixel_size(root_hwnd)
        return [DescendantInfo(root_hwnd, 'ADB', 'Android display', *(size or (0, 0)), 0, True)]

    def get_outer_pixel_size(self):
        if self._size is None:
            frame = self.screenshot()
            if frame is None:
                return None
        return self._size

    def screenshot(self):
        try:
            if not self.hwnd and not self.find_window():
                return None
            self.require_game()
            frame = self.client.capture()
            self._size = frame.shape[1], frame.shape[0]
            self.last_error = ''
            return frame
        except AdbError as exc:
            self.last_error = str(exc)
            self.hwnd = 0
            self._size = None
            logger.warning('Capture failed: %s', exc)
            return None
