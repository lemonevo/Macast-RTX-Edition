# Macast RTX Edition

[![Build Windows](https://github.com/lemonevo/Macast-RTX-Edition/actions/workflows/build-windows.yml/badge.svg)](https://github.com/lemonevo/Macast-RTX-Edition/actions/workflows/build-windows.yml)
[![GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-76b900)](LICENSE)

让 Windows、macOS 或 Linux 电脑成为局域网中的 DLNA/UPnP 投屏接收端。手机、平板或其他 DLNA 控制端发送媒体地址和播放指令，电脑用 [mpv](https://mpv.io/) 播放视频、音乐或图片。它接收媒体地址，不提供屏幕镜像。

本仓库是 [ccjjxx99/Macast-RTX-Edition](https://github.com/ccjjxx99/Macast-RTX-Edition) 的 Fork，加入了 macOS、Linux 支持和稳定性修复。**NVIDIA RTX Video VSR/HDR 仅适用于受支持的 Windows 显卡**；macOS 和 Linux 使用普通 mpv 播放。

## 平台支持

| 平台 | 从源码运行 | 本仓库的打包方式 | 播放器 |
| --- | --- | --- | --- |
| Windows | 支持 | 可构建单文件 EXE | 源码运行需自行安装 mpv；构建的 EXE 内置 mpv |
| macOS | 支持 | 暂无经过验证的 `.app`/`.dmg` | 需安装 mpv |
| Linux | 支持 | 可在 Linux 上构建单文件程序 | 需安装 mpv；图形界面还需系统托盘依赖 |

需要 **Python 3.10 或更新版本**。三个平台都支持在有图形桌面的环境中运行托盘界面；没有图形桌面时可使用命令行入口。Windows 构建脚本已验证，macOS 目前推荐源码运行，Linux 单文件构建应在与目标电脑兼容的 Linux 系统上进行。

## 主要功能

- 接收 DLNA 控制端发送的视频、音频和图片地址，支持播放、暂停、音量和进度控制。
- 使用 mpv 播放，可从托盘菜单调整窗口大小、位置、置顶和硬件解码。
- 提供本机设置页、运行日志和自定义 Renderer、Protocol、mpv 脚本支持。
- 设置页可从本仓库 [`plugins/`](plugins/README.md) 插件源一键安装 Renderer、Protocol 插件（镜像上游并带本地修复）。

## 快速开始

先将本仓库克隆到电脑，然后按自己的系统执行下面的命令：

```sh
git clone https://github.com/lemonevo/Macast-RTX-Edition.git
cd Macast-RTX-Edition
```

### Windows

安装 Python 3.10+ 和 mpv，并将 `mpv.exe` 所在目录加入 `PATH`。在 PowerShell 中执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe Macast.py
```

上例使用 Python 3.12；如果安装的是其他受支持版本，替换 `py -3.12`。需要生成内置 mpv 的 EXE，请看[中文构建指南](docs/Build_ZH.md)。原项目的 [Windows Releases](https://github.com/ccjjxx99/Macast-RTX-Edition/releases/latest) 不包含本仓库的跨平台修改。

### macOS

安装 Python 3.10+ 和 mpv（例如使用 Homebrew 安装 mpv：`brew install mpv`），然后执行：

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python Macast.py
```

应用会显示在菜单栏。仓库中的旧 `setup_py2app.py` 尚未完成当前版本的 `.app` 构建验证。

### Linux

以 Ubuntu/Debian 为例，先安装 mpv 和托盘依赖，再创建能读取系统 `gi` 模块的虚拟环境：

```sh
sudo apt install mpv python3-gi gir1.2-gtk-3.0 \
  libayatana-appindicator3-1 gir1.2-ayatanaappindicator3-0.1
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python -m pip install -e .
python Macast.py
```

其他发行版需安装对应的 mpv、GTK、PyGObject 和 AppIndicator 包。没有系统托盘时，可在安装后运行 `macast-rtx-cli`。Linux 单文件构建步骤见[中文构建指南](docs/Build_ZH.md)；生成的程序仍需目标电脑安装 mpv。

安装完成后也可以使用 `macast-rtx-gui` 启动托盘界面。源码可编辑安装需要中文菜单时，请按[构建指南](docs/Build_ZH.md)编译翻译文件。

## 如何投屏

1. 保持 Macast 运行，让电脑和控制端连接同一个局域网。
2. 在手机或其他 DLNA 控制端的设备列表中选择 Macast RTX Edition。
3. 发送媒体，电脑会通过 mpv 播放。可从托盘菜单调整窗口大小、位置、置顶和硬件解码。

投屏时电脑需要能访问控制端提供的媒体地址。如果控制端兼做媒体服务器或代理，播放期间它也需要保持在线。进度跳转取决于媒体服务器、传输协议和控制端是否支持。

### 搜不到设备？

- 确认程序仍在运行，电脑和控制端处于同一局域网。
- 检查防火墙是否允许 Macast 和 UDP 1900；Windows 可先将网络类型设为“专用网络”。
- 检查路由器是否开启访客网络、AP 隔离或客户端隔离。
- VPN、虚拟网卡和多网卡可能影响 SSDP 发现；可暂时切换到实际使用的局域网接口排查。

## Windows RTX Video

在受支持的 Windows 10/11 64 位电脑上，程序会检测 NVIDIA GeForce RTX 显卡，并提供 RTX Video Super Resolution（VSR）和 RTX Video HDR 开关。新配置检测到支持的显卡时默认开启；无法使用时会关闭 RTX 处理，普通 DLNA 播放不受影响。

VSR 仅在视频被放大时生效。RTX Video HDR 还需要 HDR 显示器以及 Windows HDR 设置。需要排查时，可检查 NVIDIA 驱动中的视频增强设置，并确认 mpv 正在使用 NVIDIA 显卡。

## 配置与构建

托盘菜单中的 `Advanced Setting` 打开本机设置页；用户脚本、配置和日志保存在系统配置目录中：

| 系统 | 配置目录 |
| --- | --- |
| Windows | `%LOCALAPPDATA%\ccjjxx99\Macast-RTX-Edition` |
| macOS | `~/Library/Application Support/Macast-RTX-Edition` |
| Linux | `~/.config/Macast-RTX-Edition` |

完整的三平台依赖、Windows EXE、Linux 单文件构建和翻译命令见[中文构建指南](docs/Build_ZH.md)；开发细节见[英文开发文档](docs/Development.md)。自定义 Renderer、Protocol 和 mpv 脚本会以当前用户权限运行，请只加载可信代码。

### 插件

托盘菜单中的 `Advanced Setting` → 设置页「插件」标签会列出**本仓库 [`plugins/`](plugins/README.md) 插件源**（[`plugins/info.json`](plugins/info.json)）里的 Renderer 和 Protocol 插件 —— 即上游 [xfangfang/Macast-plugins](https://github.com/xfangfang/Macast-plugins) 的镜像 **加上本仓库维护的修复版**（如「哔哩哔哩投屏（Bilibili 投屏）」）。点击「安装」即可下载，已安装的插件可在同一张卡片上「卸载」；两者完成后 Macast 都会自动重启以更新插件列表（当前投屏会中断），随后在托盘菜单的 `Renderers` / `Protocols` 里启用。安装和卸载只作用于白名单仓库中的 `.py` 文件（本仓库与上游插件仓库），并且只在能从本机访问设置页、且持有当前会话令牌时可用。

也可以手动安装：把插件 `.py` 放进上述配置目录的 `renderer/` 或 `protocol/` 子目录（托盘菜单 `Open Config Directory` 可直接打开），然后重启 Macast。注意插件可能只支持部分平台（例如 PotPlayer 插件仅 Windows、IINA 插件仅 macOS），插件所需的播放器或依赖要自行安装。

### 本仓库维护的插件

[`plugins/`](plugins/README.md) 是本仓库的插件源，插件商店默认从这里拉取。其中 [`plugins/nirvana.py`](plugins/README.md)（显示名 **哔哩哔哩投屏（Bilibili 投屏）**，原名 NVA Protocol）是 B 站投屏协议插件的本地维护副本，修复了弹幕状态不同步、弹幕文件互相覆盖、切换分辨率后弹幕消失、高画质无声、画质列表缺失等问题，并改为优先使用 DASH 取流（1080P 只能通过 DASH 提供，音轨由 `audio-add` 挂载），FLV 合并流作为回退。修改清单和排查方法见 [plugins/README.md](plugins/README.md)。

## 来源、许可证与感谢

本项目直接基于 [ccjjxx99/Macast-RTX-Edition](https://github.com/ccjjxx99/Macast-RTX-Edition)，其上游是 [xfangfang/Macast](https://github.com/xfangfang/Macast)。感谢 ccjjxx99、xfangfang 和所有贡献者提供基础代码及持续维护。本项目继续使用 [GNU GPL v3 或更高版本](LICENSE)；第三方组件的来源和许可证见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

问题和建议请提交到[本仓库 Issues](https://github.com/lemonevo/Macast-RTX-Edition/issues)。提交兼容性问题时，请附上操作系统、桌面环境、mpv 版本和相关日志。
