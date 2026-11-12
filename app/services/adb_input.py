"""Android taps, continuous holds/drags, menu swipes, and two-finger zoom."""
import math
import random
import time

from app.services.adb_client import AdbError
from app.services.scrcpy_control import DOWN, MOVE, UP, ScrcpyControl


class AdbInputService:
    def __init__(self, window_service, stop_event=None, *, control_factory=ScrcpyControl):
        self.window_service = window_service
        self.stop_event = stop_event
        self._control_factory = control_factory
        self._control = None
        self._serial = None
        self._held = {}

    def _check_stop(self):
        if self.stop_event is not None and self.stop_event.is_set():
            raise InterruptedError('Bot stopped by user')

    def _wait(self, seconds):
        if self.stop_event is not None:
            if self.stop_event.wait(max(0, seconds)):
                raise InterruptedError('Bot stopped by user')
        else:
            time.sleep(max(0, seconds))

    def _begin(self):
        self._check_stop()
        self.window_service.require_game()
        serial = self.window_service.client.serial
        if self._control is None or serial != self._serial:
            self.close()
            self._control = self._control_factory(self.window_service.client)
            self._serial = serial

    def _size(self):
        size = self.window_service.get_outer_pixel_size()
        if not size:
            raise AdbError(self.window_service.last_error or 'Capture the Android display before sending input.')
        return size

    def _touch(self, action, x, y, pointer=0):
        size = self._size()
        x, y = max(0, min(size[0] - 1, int(x))), max(0, min(size[1] - 1, int(y)))
        self._control.touch(action, pointer, x, y, size)
        if action == UP:
            self._held.pop(pointer, None)
        else:
            self._held[pointer] = (x, y)

    def click_at(self, x, y, rand=False):
        self._begin()
        if rand:
            x, y = x + random.randint(-15, 15), y + random.randint(-15, 15)
        self._touch(DOWN, x, y)
        try:
            self._wait(0.04)
        finally:
            self.mouse_up(x, y)

    def click(self, x, y, pause=1, rand=True):
        self.click_at(x, y, rand=rand)
        self._wait(max(0.1, random.uniform(pause * 0.8, pause * 1.2)))

    def mouse_down(self, x, y):
        self._begin()
        if 0 in self._held:
            self.mouse_up(*self._held[0])
        self._touch(DOWN, x, y)

    def mouse_up(self, x, y):
        if self._control is not None and 0 in self._held:
            # Use the last touched position for release: (0,0) is used by the
            # upstream recovery code as a sentinel, not a drag destination.
            self._touch(UP, *self._held[0])

    def move(self, x, y, wparam=0):
        self._check_stop()
        if wparam and 0 in self._held:
            self._touch(MOVE, x, y)
        # Hover is intentionally empty: Android fingers have no hover position.

    def human_move(self, x1, y1, x2, y2, duration=0.5):
        self._check_stop()
        if 0 not in self._held:
            raise AdbError('A drag must start with mouse_down().')
        duration = max(0, float(duration))
        started = time.monotonic()
        try:
            while duration and (elapsed := time.monotonic() - started) < duration:
                self._check_stop()
                t = (1 - math.cos(math.pi * elapsed / duration)) / 2
                self._touch(MOVE, x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)
                self._wait(min(1 / 60, duration - elapsed))
            self._check_stop()
            self._touch(MOVE, x2, y2)
        except BaseException:
            self._release_all()
            raise

    def scroll(self, x, y, amount, *, upward=False):
        """Scroll a menu; dragging down reveals earlier rows (wheel upward)."""
        self._check_stop()
        _, height = self._size()
        amount = max(0, int(amount))
        # Split long movements so neither endpoint crosses the Android edges.
        while amount:
            self._check_stop()
            steps = min(amount, 4)
            distance = min(height * 0.35, height * 0.08 * steps)
            middle = max(distance / 2 + 1, min(height - distance / 2 - 2, y))
            start = middle - distance / 2 if upward else middle + distance / 2
            end = middle + distance / 2 if upward else middle - distance / 2
            self.mouse_down(x, start)
            try:
                self.human_move(x, start, x, end, duration=0.3)
            finally:
                self.mouse_up(x, end)
            amount -= steps
            self._wait(0.1)

    def zoom(self, x, y, amount, *, upward=False):
        """Pinch inward to zoom out; spread to zoom in. Never pan the village."""
        amount = max(0, int(amount))
        for _ in range(math.ceil(amount / 5)):
            self._begin()
            width, height = self._size()
            radius = min(width, height) * 0.22
            cx = max(radius + 1, min(width - radius - 2, x))
            cy = max(1, min(height - 2, y))
            start, end = (radius * 0.3, radius) if upward else (radius, radius * 0.3)
            try:
                self._touch(DOWN, cx - start, cy, pointer=0)
                self._touch(DOWN, cx + start, cy, pointer=1)
                for step in range(1, 25):
                    self._check_stop()
                    r = start + (end - start) * step / 24
                    self._touch(MOVE, cx - r, cy, pointer=0)
                    self._touch(MOVE, cx + r, cy, pointer=1)
                    self._wait(1 / 60)
            finally:
                self._release_all()
            self._wait(0.1)

    def _release_all(self):
        if self._control is not None:
            self._control.release_all()
        self._held.clear()

    def close(self):
        self._release_all()
        if self._control is not None:
            self._control.close()
        self._control = None
        self._serial = None
