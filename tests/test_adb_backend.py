import os
import struct
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import cv2
import numpy as np

from app.services.adb_client import AdbClient, AdbError, Device
from app.services.adb_input import AdbInputService
from app.services.adb_window import AdbWindowService, GAME_PACKAGE
from app.services.scrcpy_control import DOWN, MOVE, UP, ScrcpyControl, touch_packet
from app.utils.window_settings_store import WindowSelection


class AdbClientTests(unittest.TestCase):
    @patch('app.services.adb_client.subprocess.run')
    def test_binary_capture_preserves_pixels_and_targets_serial(self, run):
        frame = np.zeros((30, 50, 3), np.uint8)
        frame[8, 17] = (19, 101, 231)
        run.return_value = subprocess.CompletedProcess([], 0, cv2.imencode('.png', frame)[1].tobytes(), b'')
        client = AdbClient(serial='emulator-5554', executable='/path with spaces/adb')
        np.testing.assert_array_equal(client.capture(), frame)
        self.assertEqual(run.call_args.args[0], ['/path with spaces/adb', '-s', 'emulator-5554', 'exec-out', 'screencap', '-p'])
        self.assertNotIn('shell', run.call_args.kwargs)

    def test_invalid_screenshot_fails_instead_of_returning_black_frame(self):
        client = AdbClient('test')
        client.run = Mock(return_value=b'device offline')
        with self.assertRaisesRegex(AdbError, 'invalid screenshot'):
            client.capture()

    @patch('app.services.adb_client.subprocess.run', side_effect=FileNotFoundError)
    def test_missing_adb_is_actionable(self, run):
        with self.assertRaisesRegex(AdbError, 'Install Android platform-tools'):
            AdbClient().devices()

    @patch('app.services.adb_client.subprocess.run', side_effect=subprocess.TimeoutExpired('adb', 10))
    def test_timeout_is_bounded(self, run):
        with self.assertRaisesRegex(AdbError, 'timed out'):
            AdbClient().devices()
        self.assertEqual(run.call_args.kwargs['timeout'], 10)

    def test_enumerates_only_device_lines(self):
        client = AdbClient()
        client.run = Mock(return_value=b'List of devices attached\n* daemon started successfully\nemulator-5554 device product:sdk model:Pixel\nphone unauthorized\n\n')
        self.assertEqual(client.devices(), [Device('emulator-5554', 'device', 'product:sdk model:Pixel'), Device('phone', 'unauthorized')])

    def test_multiple_devices_require_selection(self):
        client = AdbClient()
        client.devices = Mock(return_value=[Device('one', 'device'), Device('two', 'device')])
        with self.assertRaisesRegex(AdbError, 'Multiple'):
            client.select()
        self.assertEqual(client.select('two').serial, 'two')
        self.assertEqual(client.serial, 'two')

    def test_missing_or_unauthorized_pin_never_falls_back(self):
        client = AdbClient()
        client.devices = Mock(return_value=[Device('one', 'device'), Device('two', 'unauthorized')])
        for requested in ('missing', 'two'):
            with self.assertRaises(AdbError):
                client.select(requested)
        self.assertIsNone(client.serial)

    def test_foreground_does_not_match_old_task_history(self):
        client = AdbClient('test')
        client.run = Mock(return_value=b'ActivityRecord{123 u0 com.supercell.clashofclans/.Game t4}\n mResumedActivity: ActivityRecord{456 u0 com.android.settings/.Settings t5}\n')
        self.assertEqual(client.foreground_package(), 'com.android.settings')
        client.run.return_value = b'topResumedActivity=ActivityRecord{789 u0 com.supercell.clashofclans/.Game t1}'
        self.assertEqual(client.foreground_package(), GAME_PACKAGE)
        client.run.return_value = b'ActivityRecord{123 u0 com.supercell.clashofclans/.Game t4}'
        self.assertIsNone(client.foreground_package())


class CaptureTests(unittest.TestCase):
    @patch('app.services.adb_window.load_window_selection', return_value=WindowSelection())
    @patch.dict(os.environ, {}, clear=True)
    def test_capture_checks_game_and_does_not_switch_device_after_disconnect(self, selection):
        client = AdbClient(serial='emulator-5554')
        client.select = Mock()
        client.foreground_package = Mock(return_value=GAME_PACKAGE)
        client.capture = Mock(return_value=np.zeros((1080, 1920, 3), np.uint8))
        window = AdbWindowService(client=client)
        self.assertEqual(window.screenshot().shape, (1080, 1920, 3))
        self.assertEqual(window.get_outer_pixel_size(), (1920, 1080))
        client.capture.side_effect = AdbError('offline')
        self.assertIsNone(window.screenshot())
        self.assertEqual(window.hwnd, 0)
        window.find_window()
        client.select.assert_called_with('emulator-5554')

    def test_background_game_is_not_captured(self):
        client = Mock(serial='test')
        client.foreground_package.return_value = 'com.android.settings'
        window = AdbWindowService(client=client)
        window.hwnd = 'test'
        self.assertIsNone(window.screenshot())
        client.capture.assert_not_called()
        self.assertIn('Open Clash', window.last_error)


class FakeControl:
    def __init__(self, client):
        self.events = []
        self.active = {}
        self.closed = False

    def touch(self, action, pointer, x, y, size):
        self.events.append((action, pointer, x, y, size))
        if action == UP:
            self.active.pop(pointer, None)
        else:
            self.active[pointer] = (x, y, size)

    def release_all(self):
        for pointer, (x, y, size) in list(self.active.items()):
            self.touch(UP, pointer, x, y, size)

    def close(self):
        self.release_all()
        self.closed = True


class GestureTests(unittest.TestCase):
    def setUp(self):
        self.window = Mock()
        self.window.client.serial = 'test'
        self.window.get_outer_pixel_size.return_value = (1920, 1080)
        self.stop = threading.Event()
        self.control = FakeControl(self.window.client)
        self.inputs = AdbInputService(self.window, self.stop, control_factory=lambda client: self.control)

    def test_tap_clamps_and_releases(self):
        self.inputs.click_at(-500, 4000)
        self.assertEqual([(e[0], e[2], e[3]) for e in self.control.events], [(DOWN, 0, 1079), (UP, 0, 1079)])
        self.assertFalse(self.control.active)

    def test_drag_keeps_touch_down_across_segments(self):
        self.inputs.mouse_down(100, 200)
        self.inputs.human_move(100, 200, 500, 600, duration=0)
        self.inputs.human_move(500, 600, 900, 200, duration=0)
        self.inputs.mouse_up(900, 200)
        self.assertEqual([e[0] for e in self.control.events], [DOWN, MOVE, MOVE, UP])
        self.assertEqual(self.control.events[-1][2:4], (900, 200))

    def test_cancel_during_drag_releases_touch(self):
        self.inputs.mouse_down(100, 200)
        def cancel(seconds):
            self.stop.set()
            raise InterruptedError()
        self.inputs._wait = cancel
        with self.assertRaises(InterruptedError):
            self.inputs.human_move(100, 200, 500, 600, duration=0.5)
        self.assertFalse(self.control.active)
        self.assertFalse(self.inputs._held)
        self.assertEqual(self.control.events[-1][0], UP)

    def test_stopped_tap_does_not_send_anything(self):
        self.stop.set()
        with self.assertRaises(InterruptedError):
            self.inputs.click_at(100, 200)
        self.assertFalse(self.control.events)

    def test_foreground_check_precedes_tap(self):
        self.window.require_game.side_effect = AdbError('not in foreground')
        with self.assertRaises(AdbError):
            self.inputs.click_at(100, 200)
        self.assertFalse(self.control.events)

    def test_zoom_uses_two_fingers_and_releases_both(self):
        self.inputs._wait = Mock()
        self.inputs.zoom(960, 540, 5)
        down = [e for e in self.control.events if e[0] == DOWN]
        moved = [e for e in self.control.events if e[0] == MOVE]
        self.assertEqual([e[1] for e in down], [0, 1])
        self.assertLess(moved[-1][2] - moved[-2][2], down[1][2] - down[0][2])
        self.assertEqual({e[1] for e in self.control.events if e[0] == UP}, {0, 1})
        self.assertFalse(self.control.active)

    def test_close_releases_held_gesture(self):
        self.inputs.mouse_down(10, 20)
        self.inputs.close()
        self.assertFalse(self.control.active)
        self.assertTrue(self.control.closed)

    def test_scroll_direction_is_touch_direction(self):
        self.inputs._wait = Mock()
        self.inputs.human_move = Mock()
        for upward in (False, True):
            self.inputs.scroll(1200, 600, 4, upward=upward)
            _, y1, _, y2 = self.inputs.human_move.call_args.args
            self.assertEqual(y2 > y1, upward)


class ProtocolTests(unittest.TestCase):
    def test_scrcpy_touch_wire_format_matches_v5(self):
        data = touch_packet(DOWN, 1, 600, 400, (1920, 1080))
        self.assertEqual(len(data), 32)
        self.assertEqual(struct.unpack('>BBQiiHHHII', data), (2, 0, 1, 600, 400, 1920, 1080, 65535, 0, 0))
        self.assertEqual(struct.unpack('>BBQiiHHHII', touch_packet(UP, 1, 600, 400, (1920, 1080)))[7], 0)

    def test_disconnected_release_never_connects(self):
        client = AdbClient('test')
        control = ScrcpyControl(client)
        control.connect = Mock()
        control.pointers = {0: (10, 20, (1920, 1080))}
        control.release_all()
        control.connect.assert_not_called()
        self.assertFalse(control.pointers)

    def test_wrong_server_fails_before_adb_upload(self):
        client = AdbClient('test')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'server'
            path.write_bytes(b'wrong version')
            with patch('app.services.scrcpy_control.server_path', return_value=path):
                with self.assertRaisesRegex(AdbError, 'Wrong scrcpy server'):
                    ScrcpyControl(client).connect()


if __name__ == '__main__':
    unittest.main()
