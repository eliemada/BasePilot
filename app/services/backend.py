"""Select the capture/input pair before importing platform-specific modules."""
import os
import sys


def backend_name():
    backend = os.environ.get('BASEPILOT_BACKEND', 'auto').strip().lower()
    if backend == 'auto':
        return 'windows' if sys.platform == 'win32' else 'adb'
    if backend not in ('windows', 'adb'):
        raise ValueError('BASEPILOT_BACKEND must be auto, windows, or adb')
    if backend == 'windows' and sys.platform != 'win32':
        raise ValueError('The Windows backend requires Windows; use --backend adb')
    return backend
