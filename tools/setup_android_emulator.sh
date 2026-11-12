#!/usr/bin/env bash
# Ubuntu 24.04 x86_64: official Google Play AVD, CPU acceleration, software GPU.
# Install curl, unzip and openjdk-17-jre-headless first. Needs /dev/kvm access.
set -euo pipefail
SDK_DIR="${ANDROID_HOME:-$HOME/Android/Sdk}"
AVD_NAME="${BASEPILOT_AVD:-basepilot}"
IMAGE='system-images;android-35;google_apis_playstore;x86_64'
TOOLS_ZIP='commandlinetools-linux-15859902_latest.zip'
TOOLS_SHA='4e4c464f145a7512b57d088ac6c278c03c9eea610886b35a5e0804e74eedf583'
mkdir -p "$SDK_DIR/cmdline-tools"
if [ ! -x "$SDK_DIR/cmdline-tools/latest/bin/sdkmanager" ]; then
    stage=$(mktemp -d)
    trap 'rm -rf "$stage"' EXIT
    curl -fLsS --retry 3 "https://dl.google.com/android/repository/$TOOLS_ZIP" -o "$stage/tools.zip"
    printf '%s  %s\n' "$TOOLS_SHA" "$stage/tools.zip" | sha256sum -c -
    unzip -q "$stage/tools.zip" -d "$stage/unpacked"
    mv "$stage/unpacked/cmdline-tools" "$SDK_DIR/cmdline-tools/latest"
fi
export ANDROID_HOME="$SDK_DIR"
python3 - "$SDK_DIR" "$IMAGE" "$AVD_NAME" <<'PY'
from pathlib import Path
import subprocess
import sys

sdk, image, name = sys.argv[1:]
manager = str(Path(sdk) / 'cmdline-tools/latest/bin/sdkmanager')
subprocess.run([manager, '--sdk_root=' + sdk, '--licenses'], input='y\n' * 100, text=True, check=True)
subprocess.run([manager, '--sdk_root=' + sdk, 'platform-tools', 'emulator', image],
               input='y\n' * 100, text=True, check=True)
avd = Path.home() / '.android/avd' / (name + '.avd')
if not avd.exists():
    subprocess.run([str(Path(sdk) / 'cmdline-tools/latest/bin/avdmanager'), 'create', 'avd',
                    '-n', name, '-k', image, '--device', 'pixel_2'], input='no\n', text=True, check=True)
    config = avd / 'config.ini'
    values = dict(line.split('=', 1) for line in config.read_text().splitlines() if '=' in line)
    values.update({'PlayStore.enabled': 'yes', 'hw.ramSize': '3072', 'hw.cpu.ncore': '4', 'hw.gpu.enabled': 'yes',
                   'hw.gpu.mode': 'software', 'hw.lcd.width': '1080', 'hw.lcd.height': '1920',
                   'hw.lcd.density': '320', 'disk.dataPartition.size': '8G',
                   'showDeviceFrame': 'no', 'skin.dynamic': 'yes',
                   'skin.name': '1080x1920', 'fastboot.forceColdBoot': 'yes'})
    config.write_text('\n'.join(f'{k}={v}' for k, v in values.items()) + '\n')
PY
"$SDK_DIR/emulator/emulator" -accel-check
printf 'Ready. Launch with: %s/emulator/emulator -avd %s -gpu software -no-snapshot -no-audio\n' "$SDK_DIR" "$AVD_NAME"
