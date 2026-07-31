# Macast RTX Edition

[![Build Windows](https://github.com/ccjjxx99/Macast-RTX-Edition/actions/workflows/build-windows.yml/badge.svg)](https://github.com/ccjjxx99/Macast-RTX-Edition/actions/workflows/build-windows.yml)
[![GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-76b900)](LICENSE)
[![mpv 0.41.0](https://img.shields.io/badge/mpv-0.41.0-76b900)](https://github.com/mpv-player/mpv/releases/tag/v0.41.0)

Macast RTX Edition 是 [xfangfang/Macast](https://github.com/xfangfang/Macast) 的 Windows 增强版：保留轻量的 DLNA/UPnP Media Renderer，用新版 mpv 接收 OK影视、TVBox 等应用的投屏，并接入 NVIDIA RTX Video Super Resolution（VSR）与 RTX Video HDR。

当前版本：`1.0.0`。项目名称使用正确拼写 `Macast-RTX-Edition`。

## 主要变化

- 内置 mpv `0.41.0` 官方 Windows MSVC 构建，替换上游 2022 年使用的 mpv `0.34.0`。
- 托盘菜单可分别启用 RTX VSR 与 RTX Video HDR。
- VSR 会根据源视频与当前输出区域自动选择 `1.05x`～`4x` 倍率，只处理不高于 1440p、且确实发生放大的视频，避免把原生 4K 固定放大到 8K。
- RTX 模式明确使用 `gpu-next + D3D11 + d3d11va + d3d11vpp`，由 NVIDIA 驱动完成 VSR/HDR 处理。
- Python 运行与构建依赖已锁定到当前维护版本；`netifaces` 更换为兼容导入名的维护分支 `netifaces-plus`，`appdirs` 更换为 `platformdirs`。
- 移除旧管理页对 Vue 2、Vue Resource、Element UI 和远程字体的运行依赖，改为无框架、本地静态页面。
- 管理接口仅允许本机回环地址访问，并增加 CSRF 校验；旧版从局域网远程下载并执行插件的入口已移除。
- LAN 输入的 XML 禁止实体解析、DTD 与网络访问；UPnP 事件回调限制到发起订阅的控制端地址。
- Windows 构建流程使用固定提交的 GitHub Actions、固定 mpv 下载地址和 SHA-256 校验。

## 运行条件

- Windows 10/11 64 位。
- NVIDIA GeForce RTX 20 系列或更新显卡；RTX 50 系列受 NVIDIA RTX Video SDK 1.1 支持。
- 较新的 NVIDIA Game Ready 或 Studio 驱动。
- RTX Video HDR 还需要 HDR 显示器，并在 Windows“设置 → 系统 → 显示 → HDR”中打开 HDR。
- 手机与电脑处于同一局域网，路由器未启用 AP/客户端隔离。

非 RTX 电脑仍可把它当作普通 Macast 使用，但应在托盘菜单中关闭两个 RTX 选项。

## 安装与投屏

1. 从 [Releases](https://github.com/ccjjxx99/Macast-RTX-Edition/releases) 下载 `Macast-RTX-Edition-v1.0.0.exe`。
2. 启动程序；Windows 防火墙询问时，只允许“专用网络”。
3. 在系统托盘中找到 Macast RTX Edition。
4. 打开 OK影视或 TVBox 的投屏列表，选择名称中带有 `Macast RTX` 的设备。
5. 在托盘菜单的 `NVIDIA RTX Video` 分组中切换：
   - `RTX Video Super Resolution`
   - `RTX Video HDR`
6. 打开 NVIDIA App 的“系统 → 视频”，确认相应功能显示为活动状态。

RTX VSR 默认开启；RTX Video HDR 默认关闭。HDR 开启后，mpv 会把 SDR 内容交给 NVIDIA RTX Video HDR，原生 HDR 内容由驱动自动跳过转换。

## 设置与日志

托盘菜单中的“Advanced Setting”会打开本机管理页。页面提供：

- 当前本地 Renderer/Protocol 组件；
- JSON 高级设置；
- 运行日志；
- RTX 使用条件与投屏排障提示。

管理页和相关 API 只接受来自 `127.0.0.1` 或 `::1` 的请求。自定义 Renderer/Protocol 仍可放入配置目录，但插件是与主程序同权限运行的 Python 代码，只应使用自己审查过的文件。

Windows 配置目录：

```text
%LOCALAPPDATA%\ccjjxx99\Macast-RTX-Edition
```

## 从源码构建

推荐 Python 3.12。构建脚本不会清理或覆盖既有目录；目标路径已经存在时会直接停止，请为下一次构建指定新目录。

```powershell
py -3.12 -m venv .venv-rtx
.\.venv-rtx\Scripts\python.exe -m pip install -r requirements\build-windows.txt
.\scripts\fetch_mpv.ps1
.\scripts\build_windows.ps1 -Python .\.venv-rtx\Scripts\python.exe
```

默认产物：

```text
.build\windows-v1.0.0\dist\Macast-RTX-Edition-v1.0.0.exe
.build\windows-v1.0.0\dist\SHA256SUMS.txt
```

`fetch_mpv.ps1` 只接受下面这个官方资源：

```text
https://github.com/mpv-player/mpv/releases/download/v0.41.0/mpv-v0.41.0-x86_64-pc-windows-msvc.zip
SHA256: 4E197F729F5071C6772F35FFFD96E0F36E3E8A044BD9479B136BB09B7C6A80FF
```

依赖审计：

```powershell
.\.venv-rtx\Scripts\python.exe -m pip_audit -r requirements\windows.txt
```

GitHub Actions 会在每次提交和 Pull Request 上重新执行依赖审计与 Windows 构建；推送 `v*.*.*` 标签时会创建 Release 并上传 EXE 与校验文件。

## 许可证与来源

本项目是 Macast 的衍生作品，继续使用 [GNU GPL v3 或更高版本](LICENSE)。修改日期从 2026-07-31 起，主要维护者为 `ccjjxx99`。发布二进制时同时公开本仓库对应源码。

mpv 与随官方构建包含的 FFmpeg、libplacebo 等组件拥有各自许可证；准确来源、版本和再分发说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。安全问题请参阅 [SECURITY.md](SECURITY.md)。

> 本项目只提供 DLNA 接收与播放能力，不提供影视源、解析接口或内容服务。请确保投放内容及配置来源合法、可信。

<details>
<summary>查看上游 Macast 原始英文说明</summary>

<br>

<img align="center" src="macast_slogan.png" alt="slogan" height="auto"/>

# Macast

[![visitor](https://visitor-badge.glitch.me/badge?page_id=xfangfang.Macast)](https://github.com/xfangfang/Macast/releases/latest)
![stars](https://img.shields.io/badge/dynamic/json?label=github%20stars&query=stargazers_count&url=https%3A%2F%2Fapi.github.com%2Frepos%2Fxfangfang%2FMacast)
[![downloads](https://img.shields.io/github/downloads/xfangfang/Macast/total?color=blue)](https://github.com/xfangfang/Macast/releases/latest)
[![plugins](https://shields-staging.herokuapp.com/github/directory-file-count/xfangfang/Macast-plugins?type=dir&label=plugins)](https://github.com/xfangfang/Macast-plugins)
[![pypi](https://img.shields.io/pypi/v/macast)](https://pypi.org/project/macast/)
[![aur](https://img.shields.io/aur/version/macast-git?color=yellowgreen)](https://aur.archlinux.org/packages/macast-git/)
[![build](https://img.shields.io/github/workflow/status/xfangfang/Macast/Build%20Macast)](https://github.com/xfangfang/Macast/actions/workflows/build-macast.yaml)
[![mac](https://img.shields.io/badge/MacOS-10.14%20and%20higher-lightgrey?logo=Apple)](https://github.com/xfangfang/Macast/releases/latest)
[![windows](https://img.shields.io/badge/Windows-7%20and%20higher-lightgrey?logo=Windows)](https://github.com/xfangfang/Macast/releases/latest)
[![linux](https://img.shields.io/badge/Linux-Xorg-lightgrey?logo=Linux)](https://github.com/xfangfang/Macast/releases/latest)



[中文说明](README_ZH.md)

A menu bar application using mpv as **DLNA Media Renderer**. You can push videos, pictures or musics from your mobile phone to your computer.


## Installation

- ### MacOS || Windows || Debian

  Download link:  [Macast release latest](https://github.com/xfangfang/Macast/releases/latest)

- ### Package manager

  ```shell
  pip install macast
  macast-gui # or macast-cli
  ```

  Please see our wiki for more information(like **aur** support): [#package-manager](https://github.com/xfangfang/Macast/wiki/Installation#package-manager)  
  Linux users may have problems installing using pip. Two additional libraries that I have modified need to be installed:

  ```shell
  pip install git+https://github.com/xfangfang/pystray.git
  pip install git+https://github.com/xfangfang/pyperclip.git
  ```

  **See [this](https://github.com/xfangfang/Macast/wiki/Installation#linux) for Linux compatibility**

- ### Build from source

  Please refer to: [Macast Development](docs/Development.md)


## Usage

- **For ordinary users**  
After opening this app, a small icon will appear in the **menubar** / **taskbar** / **desktop panel**, then you can push your media files from a local DLNA client to your computer.

- **For advanced users**  
  1. By loading the [Macast-plugins](https://github.com/xfangfang/Macast-plugins), Macast can support third-party players like IINA and PotPlayer.  
  For more information, see: [#how-to-use-third-party-player-plug-in](https://github.com/xfangfang/Macast/wiki/FAQ#how-to-use-third-party-player-plug-in)
  2. You can modify the shortcut keys or configuration of the default mpv player by yourself, see: [#how-to-set-personal-configurations-to-mpv](https://github.com/xfangfang/Macast/wiki/FAQ#how-to-set-personal-configurations-to-mpv)

- **For developer**  
You can use a few lines of code to add support for other players like IINA and PotPlayer or even add additional features, like downloading media files while playing videos.  
Tutorials and examples are shown in: [Macast/wiki/Custom-Renderer](https://github.com/xfangfang/Macast/wiki/Custom-Renderer).  
Fell free to submit a pull request to [Macast-plugins](https://github.com/xfangfang/Macast-plugins).  


## FAQ
If you have any questions about this application, please check: [Macast/wiki/FAQ](https://github.com/xfangfang/Macast/wiki/FAQ).  
If this does not solve your problem, please open a new issue to notify us, we are willing to help you solve the problem.

## Screenshots

You can copy the video link after the video is casted：  
<img align="center" width="400" src="https://github.com/xfangfang/xfangfang.github.io/raw/master/assets/img/macast/copy_uri.png" alt="copy_uri" height="auto"/>

Or select a third-party player plug-in  
<img align="center" width="400" src="https://github.com/xfangfang/xfangfang.github.io/raw/master/assets/img/macast/select_renderer.png" alt="select_renderer" height="auto"/>

## Relevant links

[UPnP™ Device Architecture 1.1](http://upnp.org/specs/arch/UPnP-arch-DeviceArchitecture-v1.1.pdf)

[UPnP™ Resources](http://upnp.org/resources/upnpresources.zip)

[UPnP™ ContentDirectory:1 service](http://upnp.org/specs/av/UPnP-av-ContentDirectory-v1-Service.pdf)

[UPnP™ MediaRenderer:1 device](http://upnp.org/specs/av/UPnP-av-MediaRenderer-v1-Device.pdf)

[UPnP™ AVTransport:1 service](http://upnp.org/specs/av/UPnP-av-AVTransport-v1-Service.pdf)

[UPnP™ RenderingControl:1 service](http://upnp.org/specs/av/UPnP-av-RenderingControl-v1-Service.pdf)

[python-upnp-ssdp-example](https://github.com/ZeWaren/python-upnp-ssdp-example)

</details>
