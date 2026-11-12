"""Read-only Linux/Android readiness report, usable without a display server."""
import hashlib
import json
import os
from pathlib import Path
import time

import cv2
import pytesseract

from app.config import resolve_aspect_key
from app.services.adb_client import AdbClient, AdbError
from app.services.adb_window import GAME_PACKAGE
from app.services.scrcpy_control import SERVER_SHA256, server_path
from app.utils.window_settings_store import load_window_selection


def diagnose_android(screenshot_path=None):
    report = {'transport_ok': False, 'game_ready': False, 'ocr_ready': False}
    try:
        report['tesseract'] = str(pytesseract.get_tesseract_version())
        report['ocr_ready'] = 'eng' in pytesseract.get_languages(config='')
    except Exception as exc:
        report['ocr_error'] = str(exc)
    helper = server_path()
    report['touch_helper_ready'] = helper.is_file() and hashlib.sha256(helper.read_bytes()).hexdigest() == SERVER_SHA256
    try:
        client = AdbClient()
        report['devices'] = [vars(d) for d in client.devices()]
        saved = load_window_selection()
        requested = os.environ.get('BASEPILOT_ADB_SERIAL') or (saved.title if saved.top_class == 'ADB' else None)
        client.select(requested)
        report['serial'] = client.serial
        report['foreground_package'] = client.foreground_package()
        start = time.monotonic()
        frame = client.capture()
        report['capture_ms'] = round((time.monotonic() - start) * 1000, 1)
        report['resolution'] = [frame.shape[1], frame.shape[0]]
        report['aspect'] = resolve_aspect_key(*report['resolution'])
        report['transport_ok'] = True
        report['game_ready'] = report['foreground_package'] == GAME_PACKAGE and report['aspect'] is not None
        if screenshot_path:
            path = Path(screenshot_path).expanduser()
            if not cv2.imwrite(str(path), frame):
                raise AdbError(f'Could not save screenshot to {path}')
            report['screenshot'] = str(path)
    except (AdbError, OSError, cv2.error) as exc:
        report['error'] = str(exc)
    print(json.dumps(report, indent=2))
    return 0 if report['transport_ok'] and report['ocr_ready'] and report['touch_helper_ready'] else 1
