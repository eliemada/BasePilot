import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class LinuxStartupTests(unittest.TestCase):
    @patch.dict(os.environ, {'BASEPILOT_BACKEND': 'adb'})
    def test_gui_imports_without_windows_dlls(self):
        from app.ui.qt.main_window import MainWindow
        from app.services.display import DisplayService
        self.assertIsNotNone(MainWindow)
        self.assertFalse(DisplayService().restore_if_pending())

    @patch.dict(os.environ, {}, clear=True)
    @patch('app.utils.tesseract_env.sys.platform', 'linux')
    @patch('app.utils.tesseract_env.shutil.which', return_value='/usr/bin/tesseract')
    def test_linux_tesseract_uses_its_packaged_data(self, which):
        import pytesseract
        from app.utils.tesseract_env import configure_tesseract
        configure_tesseract()
        self.assertEqual(pytesseract.pytesseract.tesseract_cmd, '/usr/bin/tesseract')
        self.assertNotIn('TESSDATA_PREFIX', os.environ)

    @patch.dict(os.environ, {'TESSERACT_CMD': '/usr/bin/tesseract', 'TESSDATA_PREFIX': '/custom/data'}, clear=True)
    def test_explicit_tesseract_data_is_preserved(self):
        from app.utils.tesseract_env import configure_tesseract
        configure_tesseract()
        self.assertEqual(os.environ['TESSDATA_PREFIX'], '/custom/data')

    def test_malformed_device_selection_returns_empty_identity(self):
        from app.utils.window_settings_store import load_window_selection
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'window.json'
            path.write_text('{not json')
            with patch('app.utils.window_settings_store.get_window_selection_path', return_value=path):
                self.assertFalse(load_window_selection().is_set())
