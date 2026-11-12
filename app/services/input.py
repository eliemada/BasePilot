"""Public input interface; always selects the same backend as capture."""
from app.services.backend import backend_name

if backend_name() == 'adb':
    from app.services.adb_input import AdbInputService as InputService
else:
    from app.services.windows_input import InputService
