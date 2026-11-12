"""Public capture interface. Linux uses Android devices connected through ADB."""
from app.services.backend import backend_name
from app.services.window_models import DescendantInfo, WindowCandidate

# Kept for existing Windows input callers.
WM_LBUTTONDOWN, WM_LBUTTONUP, WM_MOUSEMOVE = 513, 514, 512
MK_LBUTTON, WM_MOUSEWHEEL, WHEEL_DELTA = 1, 522, 120

if backend_name() == 'adb':
    from app.services.adb_window import AdbWindowService as WindowService
else:
    from app.services.windows_window import WindowService
