# Linux and Android over ADB

This fork runs the Qt app, vision, OCR and bot logic natively on Linux. The game
runs on an Android device or emulator connected through ADB. Google Play Games
for Windows is not used by this backend.

The first deployment uses Ubuntu 24.04 in Unraid, with 4 vCPUs, 6 GiB RAM and a
64 GiB sparse SSD disk. Android 15 runs inside it with KVM and software graphics.
This boots without GPU passthrough. Game performance and compatibility must be
tested separately; a successful Android boot is not proof that Clash works.

**Current result, 2026-11-12:** the Play Store build of Clash 18.647.5 installs
but exits during startup in this VM. The same unmodified build also exits in
Waydroid/Android 13. The instructions below reproduce the Linux app and Android
transport setup; farming has not been demonstrated in either tested runtime.

## Install BasePilot

Use Python 3.11 or later. On Ubuntu 24.04:

```bash
sudo apt-get update
sudo apt-get install -y python3-venv git adb tesseract-ocr tesseract-ocr-eng \
  libgl1 libegl1 libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 \
  libxkbcommon-x11-0 libxcb-xinerama0
git clone --branch linux-adb https://github.com/eliemada/BasePilot.git
cd BasePilot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python tools/install_scrcpy.py
```

The installer downloads **scrcpy-server v5.0.1** from Genymobile's official
release and verifies its SHA-256. The protocol is version-specific; an arbitrary
distribution-provided scrcpy server is not interchangeable. The server is an
Apache-2.0 component downloaded separately, not vendored into this repository.
It runs under the Android debugging user and does not require root. Only its
control channel is enabled. Screenshots use `adb exec-out screencap -p`.

Linux needs only PySide6 Essentials and headless OpenCV. The GUI still runs on
your normal X11/Wayland desktop. Tesseract uses the installed Linux executable
and its packaged English language data.

## Choose an Android runtime

An existing Android device, Waydroid, or the official Android Emulator can work
with the transport. They are not equivalent in game compatibility. Clash needs
to install and launch successfully before BasePilot can operate it. This fork
does not change Android integrity checks or game clients.

For the official Android Emulator on an x86_64 Ubuntu VM:

1. Use host CPU passthrough and expose Intel VMX or AMD SVM. Check that `/dev/kvm`
   exists in the Linux guest and your user belongs to the `kvm` group.
2. Install the command-line dependencies and create the AVD:

   ```bash
   sudo apt-get install -y curl unzip openjdk-17-jre-headless
   bash tools/setup_android_emulator.sh
   ```

   The script downloads Google's command-line tools, accepts the SDK licenses,
   and installs the Android 15 Google Play x86_64 image and emulator. It creates
   an AVD called `basepilot`, with 3 GiB Android RAM and software graphics.
   It leaves an existing AVD unchanged.
3. Start it from the Linux desktop:

   ```bash
   export ANDROID_HOME="$HOME/Android/Sdk"
   export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH"
   emulator -avd basepilot -gpu software -no-snapshot -no-audio
   ```

   Nested virtualization is experimental for the Android Emulator. Its
   `-accel-check` must pass, but that does not guarantee good game performance.
4. Sign in to Google Play and install/open Clash of Clans. The tested image
   advertises `x86_64,arm64-v8a`; no third-party ARM translator was installed.
5. Use landscape 16:9 or 16:10, for example 1920×1080. To reduce software
   rendering load, a 1280×720 landscape display is also supported. An emulator
   with a portrait base display rotates when the game opens. Optional:

   ```bash
   adb -s emulator-5554 shell wm size 720x1280
   adb -s emulator-5554 shell wm density 240
   ```

   Restore with `wm size reset` and `wm density reset`. Keep Android navigation
   and status bars out of the game capture (the game normally uses immersive
   fullscreen). A different HUD layout can require template or coordinate work.

On Unraid, use a VirtIO network adapter on `virbr0` (NAT) or your LAN bridge.
Ubuntu already includes the driver; there is no Windows network-setup screen.
NAT guests can be administered through SSH via the Unraid host, and the desktop
through the VM's VNC console. The VM and Android emulator do not need a Wi-Fi
adapter. Software graphics avoids taking a GPU away from other host workloads.

When defining the Unraid VM through libvirt XML, the VNC graphics device also
needs `websocket='-1'` alongside `autoport='yes'`. Otherwise Unraid's noVNC link
can point to `/wsproxy/0/` and fail even though the VM and VNC server are running.
After correcting this, refresh the VMs page and open a new VNC tab.

## Validate before starting

```bash
adb devices -l
export BASEPILOT_ADB="$HOME/Android/Sdk/platform-tools/adb"  # if using the SDK
.venv/bin/python main.py --backend adb --device emulator-5554 \
  --diagnose --screenshot /tmp/basepilot-android.png
.venv/bin/python main.py --backend adb --device emulator-5554
```

Diagnostics are read-only and work without a Linux display server. They report
the selected device, foreground package, screenshot dimensions and latency,
Tesseract availability, and the touch helper checksum. `transport_ok: true` only
means an Android screenshot was captured. `game_ready: true` additionally means
Clash is in the foreground and the aspect ratio is supported; it does not claim
that templates, battle strategies or upgrades have been validated.

In Settings → Android device, Refresh lists the ADB devices. Test checks capture
dimensions; Use this device persists its serial. A command-line `--device` or
`BASEPILOT_ADB_SERIAL` takes precedence over the picker. With no selection, only
one authorized device may be connected. A missing pinned device is an error;
the bot never silently switches to another device after disconnection.

Open the Home Village and start with auto-upgrades set to **Dry run**, watching
the existing logs and template detection. This setting only prevents upgrade
execution: starting the bot still farms and sends input. Use `--diagnose` for a
strictly read-only first check. Farming, wall changes and account switching are
not automatically started by installing this fork.

## Input semantics

- Screenshots remain OpenCV BGR arrays at Android display coordinates.
- Mouse down/move/up become a continuous Android touch, so troop deployment
  keeps a finger held across multiple movement segments.
- Menu wheel actions become vertical swipes. Village zoom has a separate
  `zoom()` operation using two fingers; replacing every wheel action with a
  swipe would pan the village instead of zooming it.
- Touches are released after cancellation/errors and when a run exits.
- The bot checks that `com.supercell.clashofclans` is in the foreground before
  capture and before beginning a gesture. Raw device diagnostics can capture
  other apps but do not send input.
- ADB commands have timeouts. Device serials and executable paths are passed as
  subprocess arguments. scrcpy forwards bind locally and are removed on close.
- Windows taskbar actions and host display switching are unused on Linux.

Configuration: `BASEPILOT_BACKEND=adb|windows|auto`, `BASEPILOT_ADB`,
`BASEPILOT_ADB_SERIAL`, and `BASEPILOT_SCRCPY_SERVER`. Non-Windows systems default
to ADB; Windows defaults to the existing Google Play Games backend. Native Linux
settings and logs live under `~/.local/share/BasePilot/`.

## Checks and current limits

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Tests cover device ambiguity/offline states, binary PNG decoding and BGR pixels,
foreground detection, continuous drag segments, cancellation, pinch direction,
scroll direction, touch packet encoding, helper verification, Linux imports and
OCR configuration, plus the upstream upgrade/event regression tests.

Live Unraid validation has confirmed Android boot, native Qt startup (after
installing the XCB libraries above), screenshots, OCR availability, and two
simultaneous injected fingers visible in Android's pointer overlay. The 40-test
suite passed on the Ubuntu guest and fresh Linux and Windows CI runners.

The game compatibility test used Clash **18.647.5**, version code **180647006**,
with its native **x86_64** libraries:

| Runtime on the Ubuntu VM | Installation | ADB screenshot sample | Game launch |
| --- | --- | --- | --- |
| Official Android 15 / API 35 Google Play Emulator, KVM + software graphics | Google Play, signed in | 720×1280, about 2.4 s | Exits during startup |
| Waydroid, LineageOS 20 / Android 13 GAPPS, SwiftShader under nested Weston | Same five unchanged APK components from the Play Store installation | 1280×720, about 0.31 s | Exits during startup |

Both launch attempts report `smxuhbhxh.ae: 02` while initializing the app factory
through `Runtime.nativeLoad` / `System.loadLibrary`. In the official emulator,
the native library load is logged as successful before the app raises the
exception. The precise reason for that internal exception is unknown. It is
not evidence that every Linux runtime is incompatible, and changing BasePilot's
capture code does not resolve this startup failure.

No village, template matching, troop deployment, or upgrades have been validated
in these runtimes. No Windows live-game regression test has been performed.
The next gameplay test needs a runtime or device where this Clash build actually
opens. Keep `--diagnose` separate from a farming run; its transport success does
not establish game compatibility.

An additional official-emulator console screenshot benchmark took about 0.22 s,
but returned the physical 1080×1920 display while ADB used the overridden
720×1280 coordinates. That alternative is not enabled in this fork; rotation
and touch-coordinate mapping would need validation before using it.

References: [Android Emulator acceleration](https://developer.android.com/studio/run/emulator-acceleration),
[Google's SDK tools](https://developer.android.com/studio),
[Waydroid in a VM](https://docs.waydro.id/faq/get-waydroid-to-work-through-a-vm),
[scrcpy v5.0.1 protocol](https://github.com/Genymobile/scrcpy/blob/v5.0.1/app/src/control_msg.c).
