# Third-party notices

Macast RTX Edition is a derivative of [xfangfang/Macast](https://github.com/xfangfang/Macast), originally distributed under GNU GPL v3. The original copyright notices are retained in source files and the repository history.

## Bundled mpv binary

Windows releases bundle the unmodified official mpv `v0.41.0-dev-g63ada87ec` x86-64 MSVC development asset:

- Binary archive: `mpv-v0.41.0-dev-g63ada87ec-30636475556-x86_64-pc-windows-msvc.zip`
- Rolling release: <https://github.com/mpv-player/mpv/releases/tag/git-release>
- Corresponding source commit: <https://github.com/mpv-player/mpv/tree/63ada87ec>
- SHA-256: `B195E12366FC95EABF22A0D409C160069BB222371C7F4570C2CEF7B217EE80F7`
- mpv license information: <https://github.com/mpv-player/mpv/blob/63ada87ec/Copyright>

The official mpv build reports FFmpeg, libplacebo, and other linked components at runtime with `mpv.exe --version`. Their corresponding source and build configuration are available through the pinned mpv source commit and mpv's CI configuration.

## Direct Python runtime dependencies

The Windows executable also contains Python and these directly declared packages:

| Component | Version | License family | Project |
| --- | ---: | --- | --- |
| Python | 3.12 | PSF License | <https://www.python.org/> |
| CherryPy | 18.10.0 | BSD | <https://github.com/cherrypy/cherrypy> |
| lxml | 6.1.1 | BSD-3-Clause | <https://github.com/lxml/lxml> |
| netifaces-plus | 0.12.5 | MIT | <https://pypi.org/project/netifaces-plus/> |
| packaging | 26.2 | Apache-2.0 or BSD-2-Clause | <https://github.com/pypa/packaging> |
| Pillow | 12.3.0 | HPND | <https://python-pillow.org/> |
| platformdirs | 4.11.0 | MIT | <https://github.com/tox-dev/platformdirs> |
| pyperclip | 1.11.0 | BSD | <https://github.com/asweigart/pyperclip> |
| pystray | 0.19.5 | LGPL-3.0-only | <https://github.com/moses-palmer/pystray> |
| requests | 2.34.2 | Apache-2.0 | <https://requests.readthedocs.io/> |

Transitive packages retain their own metadata and license files inside the Python distribution or build environment. `pip-audit` is run against the resolved dependency graph in CI; it is a security check, not a license-compatibility certification.

## Third-party plugins

The `plugins/` directory is the plugin source used by the settings page (see [plugins/README.md](plugins/README.md)). It mirrors the renderer/protocol plugins published by [xfangfang/Macast-plugins](https://github.com/xfangfang/Macast-plugins) and keeps locally patched copies where needed:

| File | Author | Notes |
| --- | --- | --- |
| `plugins/nirvana.py` | xfangfang | Locally patched copy (v0.34) of the bilibili NVA protocol plugin, shown as **哔哩哔哩投屏（Bilibili 投屏）**. Fixes danmaku state sync, per-video danmaku files, danmaku parsing robustness, resolution-switch danmaku loss, DASH audio attachment, quality list fallback, quality downgrade reporting, and several crash paths. |
| `plugins/iina.py`, `plugins/web.py`, `plugins/potplayer.py`, `plugins/live.py` | xfangfang, dushan555 (`live.py`) | Unmodified copies of the upstream plugins (only the download URLs differ). |
| `plugins/pi_fm.py` | xfangfang | Unmodified upstream plugin for Raspberry Pi FM transmission. |

Upstream notice: the plugin scripts are distributed by their authors for programming study only and marked as not for commercial use; the original copyright headers and source links are retained in each file. Confirm with the authors before redistributing or using them commercially.

