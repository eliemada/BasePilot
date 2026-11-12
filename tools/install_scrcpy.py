"""Download the pinned Android touch helper from the official scrcpy release."""
import hashlib
from pathlib import Path
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.scrcpy_control import SERVER_SHA256, SERVER_URL, server_path


def main():
    path = server_path()
    if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == SERVER_SHA256:
        print(f'Already installed: {path}')
        return
    with urllib.request.urlopen(SERVER_URL, timeout=60) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != SERVER_SHA256:
        raise RuntimeError('scrcpy server checksum mismatch; download discarded')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.download')
    temporary.write_bytes(data)
    temporary.replace(path)
    print(f'Installed and verified: {path}')


if __name__ == '__main__':
    main()
