# Build and run Macast RTX Edition

Run all commands from the repository root. Use Python 3.10 or newer. Install
system `mpv` before starting the app on macOS or Linux. Windows source runs
also need `mpv.exe` on `PATH`; the Windows binary build downloads and bundles
its own verified mpv.

| System | Source GUI | Headless CLI | Standalone build |
| --- | --- | --- | --- |
| Windows | `python Macast.py` | `macast-rtx-cli` | `scripts/build_windows.ps1` |
| macOS | `python Macast.py` | `macast-rtx-cli` | Source installation is the supported path |
| Linux | `python Macast.py` | `macast-rtx-cli` | `scripts/build_linux.sh` |

The GUI entry point installed by pip is `macast-rtx-gui`. `Macast.py` and this
entry point use the same initialization code. Windows alone has NVIDIA RTX
Video VSR/HDR controls; macOS and Linux use ordinary mpv playback.

## Windows

In PowerShell, install Python 3.12, then:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe Macast.py
```

To build the standalone executable, use a fresh environment with the pinned
build dependencies:

```powershell
py -3.12 -m venv .venv-build
.\.venv-build\Scripts\python.exe -m pip install -r requirements\build-windows.txt
.\scripts\build_windows.ps1 -Python .\.venv-build\Scripts\python.exe
```

The script downloads the verified Windows mpv build, compiles translation
catalogs, includes application assets, and writes an EXE plus
`SHA256SUMS.txt` under `.build/windows-v<version>/dist/`. It refuses to
replace an existing output directory; pass a new `-OutputRoot` for another
build.

## macOS

Install Python 3.10 or newer and `mpv`, then:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python Macast.py
```

The installed `macast-rtx-gui` and `macast-rtx-cli` commands work from any
working directory. This repository also retains `setup_py2app.py` from the
original project, but its `.app` output has not been validated with the
current cross-platform changes. Use the source installation for macOS until
that bundle is verified.

## Linux (Ubuntu/Debian example)

Install `mpv` and a tray backend. GNOME Wayland needs the system `gi` and
AppIndicator modules to be visible inside the virtual environment:

```sh
sudo apt install mpv python3-gi gir1.2-gtk-3.0 \
  libayatana-appindicator3-1 gir1.2-ayatanaappindicator3-0.1
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python -m pip install -e .
python Macast.py
```

On other distributions, install the equivalent `mpv`, GTK, PyGObject and
AppIndicator packages. On GNOME Wayland, check that
`python -c 'import pystray; print(pystray.Icon.__module__)'` prints
`pystray._appindicator`. If it prints `pystray._xorg`, recreate the virtual
environment with `--system-site-packages`. Quit any old Macast process before
restarting; each process creates a separate tray icon. On desktops without a
tray, use `macast-rtx-cli` instead of the GUI. Linux uses system `mpv`, even
for a standalone build.

To build a Linux one-file executable:

```sh
python -m pip install -r requirements/build-linux.txt
./scripts/build_linux.sh
```

The output is `.build/linux-v<version>-<architecture>/dist/` with a binary
and `SHA256SUMS.txt`. Pass a new output directory as the script's first
argument for a second build. The target machine still needs `mpv` and a
supported desktop tray backend. Build on the same Linux architecture and a
compatible system version as the target machine.

## Translation catalogs

Wheels and standalone builds compile the catalogs from `i18n/*/LC_MESSAGES/`
automatically. For an editable source installation, English works without a
catalog. To enable other languages from the checkout, compile the matching
`.po` file in place with `msgfmt`, for example:

```sh
msgfmt -o i18n/zh_CN/LC_MESSAGES/macast.mo \
  i18n/zh_CN/LC_MESSAGES/macast.po
```

## Check a build

Start only one Macast process. Confirm the tray menu opens, select the device
from a DLNA controller on the same LAN, and try a media URL. Linux discovery
uses UDP 1900; the app serves the device description on its configured TCP
port. Firewalls and Wi-Fi client isolation can prevent discovery even when the
app starts normally. Logs and settings are in the user configuration directory
shown by the tray's **Open Config Directory** action.

The local settings page (`http://127.0.0.1:<port>`) is loopback-only. Its
**Plugins** tab lists the plugin source in `plugins/` (this repository's mirror of
`xfangfang/Macast-plugins` plus local patches) through
`macast/plugin_store.py` and installs the selected file into
`<config dir>/renderer` or `<config dir>/protocol`. Installing restarts the
whole application, because plugins are imported during startup; confirm the new
entry in the tray menu afterwards.
