# 按系统编译和运行

先克隆仓库并进入项目根目录。Python 需为 3.10 或更新版本。安装后可用
`macast-rtx-gui` 启动托盘界面，或用 `macast-rtx-cli` 在无图形桌面的环境中运行。
三个平台也都可以在仓库根目录执行 `python Macast.py` 启动界面。

## Windows

源码运行需要先安装 mpv，并把 `mpv.exe` 所在目录加入 `PATH`。推荐 Python 3.12。
在 PowerShell 中执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe Macast.py
```

生成带内置 mpv 的单文件 EXE：

```powershell
py -3.12 -m venv .venv-build
.\.venv-build\Scripts\python.exe -m pip install -r requirements\build-windows.txt
.\scripts\build_windows.ps1 -Python .\.venv-build\Scripts\python.exe
```

产物位于 `.build/windows-v<版本>/dist/`。脚本会校验下载的 mpv，且不会覆盖旧的构建目录；重复构建时传入新的 `-OutputRoot`。

## macOS

先安装 Python 3.10+ 和 mpv，确保终端中能运行 `mpv --version`。然后执行：

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python Macast.py
```

macOS 目前推荐以上源码安装方式。仓库中的旧 `setup_py2app.py` 尚未对当前版本完成 `.app` 构建验证。

## Linux（Ubuntu/Debian 示例）

先安装 mpv 和托盘依赖。GNOME Wayland 的虚拟环境需要通过
`--system-site-packages` 读取系统的 `gi` 模块：

```sh
sudo apt install mpv python3-gi gir1.2-gtk-3.0 \
  libayatana-appindicator3-1 gir1.2-ayatanaappindicator3-0.1
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python -m pip install -e .
python Macast.py
```

其他发行版安装对应的 mpv、GTK、PyGObject 和 AppIndicator 包。GNOME Wayland 下可执行以下命令检查托盘后端：

```sh
python -c 'import pystray; print(pystray.Icon.__module__)'
```

输出应为 `pystray._appindicator`。若显示 `pystray._xorg`，请重新创建带
`--system-site-packages` 的虚拟环境。启动前退出旧 Macast 进程，避免出现多个图标。
无托盘的桌面可运行 `macast-rtx-cli`。

生成 Linux 单文件可执行程序：

```sh
python -m pip install -r requirements/build-linux.txt
./scripts/build_linux.sh
```

产物位于 `.build/linux-v<版本>-<架构>/dist/`。目标电脑仍需安装 mpv，图形界面还需可用的托盘后端。请在与目标电脑兼容的 Linux 版本和架构上构建。

## 翻译与验证

wheel 和单文件构建会自动编译翻译文件。源码可编辑安装如果需要中文菜单，可先安装 gettext 并执行：

```sh
msgfmt -o i18n/zh_CN/LC_MESSAGES/macast.mo \
  i18n/zh_CN/LC_MESSAGES/macast.po
```

启动后确认托盘菜单能打开，且手机和电脑在同一局域网。Linux 的设备发现使用 UDP 1900；防火墙或 Wi-Fi 客户端隔离可能导致搜不到设备。详细说明见 [英文开发文档](Development.md)。
