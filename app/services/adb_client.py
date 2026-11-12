"""Bounded ADB commands with explicit device selection and binary captures."""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass

import cv2
import numpy as np


class AdbError(RuntimeError):
    pass


@dataclass(frozen=True)
class Device:
    serial: str
    state: str
    description: str = ''


class AdbClient:
    def __init__(self, serial=None, executable=None, timeout=10):
        self.serial = serial
        self.executable = executable or os.environ.get('BASEPILOT_ADB', 'adb')
        self.timeout = timeout

    def command(self, *args, target=True):
        cmd = [self.executable]
        if target:
            if not self.serial:
                raise AdbError('Select an Android device first.')
            cmd += ['-s', self.serial]
        return cmd + list(args)

    def run(self, *args, target=True, timeout=None):
        cmd = self.command(*args, target=target)
        try:
            result = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout or self.timeout,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except FileNotFoundError as exc:
            raise AdbError('ADB was not found. Install Android platform-tools or set BASEPILOT_ADB.') from exc
        except subprocess.TimeoutExpired as exc:
            raise AdbError(f'ADB timed out ({args[0] if args else "command"}); check the Android device.') from exc
        except OSError as exc:
            raise AdbError(f'Could not start ADB: {exc}') from exc
        if result.returncode:
            message = result.stderr.decode('utf-8', errors='replace').strip()
            raise AdbError(f'ADB failed: {message or result.returncode}')
        return result.stdout

    def devices(self):
        result = []
        for line in self.run('devices', '-l', target=False).decode(errors='replace').splitlines():
            fields = line.split(maxsplit=2)
            if not fields or line.startswith(('List of devices', '*')) or len(fields) < 2:
                continue
            result.append(Device(fields[0], fields[1], fields[2] if len(fields) > 2 else ''))
        return result

    def select(self, requested=None):
        devices = self.devices()
        if requested:
            match = next((d for d in devices if d.serial == requested), None)
            if not match:
                raise AdbError(f'Android device {requested!r} is not connected.')
            if match.state != 'device':
                raise AdbError(f'Android device {requested!r} is {match.state}. Unlock it and authorize USB debugging.')
        else:
            available = [d for d in devices if d.state == 'device']
            if len(available) != 1:
                if available:
                    raise AdbError('Multiple Android devices are connected. Pick one in Settings or use --device SERIAL.')
                states = ', '.join(f'{d.serial}: {d.state}' for d in devices)
                raise AdbError('No authorized Android device. Start the emulator or connect a device.' +
                               (f' ({states})' if states else ''))
            match = available[0]
        self.serial = match.serial
        return match

    def foreground_package(self):
        output = self.run('shell', 'dumpsys', 'activity', 'activities').decode(errors='replace')
        # Android versions use different field names. Only resumed activities count;
        # a package appearing elsewhere in a task history is not a foreground match.
        matches = re.findall(r'(?:topResumedActivity|mResumedActivity|ResumedActivity):?\s*=?\s*'
                             r'ActivityRecord\{[^\n}]*?\s([\w.]+)/', output)
        if matches:
            return matches[-1]
        return None

    def capture(self):
        data = self.run('exec-out', 'screencap', '-p')
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise AdbError('Android returned an invalid screenshot (expected PNG).')
        frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None or not frame.size:
            raise AdbError('Could not decode the Android screenshot.')
        return frame
