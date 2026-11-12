"""Small control-only scrcpy client carried over a local ADB forward.

Wire format pinned to Genymobile/scrcpy v5.0.1, app/src/control_msg.c.
No video stream, root, or persistent Android installation is needed.
"""
from __future__ import annotations

import atexit
import hashlib
import os
from pathlib import Path
import secrets
import socket
import struct
import subprocess
import tempfile
import time

from app.services.adb_client import AdbError
from app.utils.common import get_user_app_data_dir

SERVER_VERSION = '5.0.1'
SERVER_SHA256 = '764eb6f79811d5211fe9df341120882ba9994c7a61b897d7bf3fb662e53bc536'
SERVER_URL = f'https://github.com/Genymobile/scrcpy/releases/download/v{SERVER_VERSION}/scrcpy-server-v{SERVER_VERSION}'
DOWN, UP, MOVE = 0, 1, 2


def server_path():
    return Path(os.environ.get('BASEPILOT_SCRCPY_SERVER') or
                get_user_app_data_dir() / f'scrcpy-server-v{SERVER_VERSION}')


def touch_packet(action, pointer, x, y, size):
    width, height = size
    if not (0 < width <= 65535 and 0 < height <= 65535):
        raise ValueError('Invalid Android display size')
    x, y = max(0, min(width - 1, int(x))), max(0, min(height - 1, int(y)))
    return struct.pack('>BBQiiHHHII', 2, action, pointer, x, y, width, height,
                       0 if action == UP else 65535, 0, 0)


class ScrcpyControl:
    def __init__(self, client):
        # Keep the selected serial fixed throughout this connection.
        from app.services.adb_client import AdbClient
        self.client = AdbClient(serial=client.serial, executable=client.executable)
        self.socket = None
        self.process = None
        self.port = None
        self.log = None
        self.remote_path = None
        self.pointers = {}

    def connect(self):
        if self.socket is not None:
            return
        path = server_path()
        if not path.is_file():
            raise AdbError('Touch support is not installed. Run: python tools/install_scrcpy.py')
        if hashlib.sha256(path.read_bytes()).hexdigest() != SERVER_SHA256:
            raise AdbError(f'Wrong scrcpy server: expected v{SERVER_VERSION}. Run tools/install_scrcpy.py.')
        scid = secrets.randbits(31)
        self.remote_path = f'/data/local/tmp/basepilot-scrcpy-{scid:08x}.jar'
        try:
            self.client.run('push', str(path), self.remote_path, timeout=30)
            self.port = int(self.client.run('forward', 'tcp:0', f'localabstract:scrcpy_{scid:08x}').strip())
            self.log = tempfile.TemporaryFile()
            command = self.client.command('shell', f'CLASSPATH={self.remote_path}',
                'app_process', '/', 'com.genymobile.scrcpy.Server', SERVER_VERSION,
                f'scid={scid:08x}', 'video=false', 'audio=false', 'control=true',
                'tunnel_forward=true', 'send_device_meta=false', 'send_dummy_byte=true',
                'clipboard_autosync=false', 'power_on=false', 'log_level=warn', 'cleanup=true')
            self.process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=self.log,
                                            stderr=subprocess.STDOUT,
                                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    self.log.seek(0)
                    detail = self.log.read(3000).decode(errors='replace')
                    raise AdbError(f'Android touch server exited: {detail}')
                sock = None
                try:
                    sock = socket.create_connection(('127.0.0.1', self.port), timeout=0.5)
                    if sock.recv(1) == b'\x00':
                        sock.settimeout(2)
                        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                        self.socket = sock
                        atexit.register(self.close)
                        return
                except OSError:
                    pass
                if sock is not None:
                    sock.close()
                time.sleep(0.1)
            raise AdbError('Android touch server did not become ready within 10 seconds.')
        except Exception:
            self.close()
            raise

    def touch(self, action, pointer, x, y, size):
        self.connect()
        try:
            self.socket.sendall(touch_packet(action, pointer, x, y, size))
        except OSError as exc:
            self.close()
            raise AdbError('Android touch connection was lost; stopped this run.') from exc
        if action == UP:
            self.pointers.pop(pointer, None)
        else:
            self.pointers[pointer] = (x, y, size)

    def release_all(self):
        # No reconnect, foreground check or cancellation check during release.
        for pointer, (x, y, size) in list(self.pointers.items()):
            try:
                if self.socket:
                    self.socket.sendall(touch_packet(UP, pointer, x, y, size))
            except OSError:
                pass
        self.pointers.clear()

    def close(self):
        self.release_all()
        if self.socket is not None:
            self.socket.close()
            self.socket = None
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
            self.process = None
        if self.port is not None:
            try:
                self.client.run('forward', '--remove', f'tcp:{self.port}', timeout=2)
            except AdbError:
                pass
            self.port = None
        if self.log is not None:
            self.log.close()
            self.log = None
        atexit.unregister(self.close)
