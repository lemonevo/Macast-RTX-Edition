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
