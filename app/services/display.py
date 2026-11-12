"""Host display switching is only needed for Google Play Games on Windows."""
from app.services.backend import backend_name

if backend_name() == 'windows':
    from app.services.windows_display import DisplayService
else:
    class DisplayService:
        def current_size(self):
            return None

        def is_16_9(self):
            return False

        def has_pending_restore(self):
            return False

        def restore_if_pending(self):
            return False

        def switch_to_16_9(self):
            return False, None, 'configure_android_display'

        def restore(self):
            return False, None, 'nothing_to_restore'
