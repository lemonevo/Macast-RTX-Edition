# 📺 Macast RTX Edition

[![Latest release](https://img.shields.io/github/v/release/ccjjxx99/Macast-RTX-Edition?display_name=tag&sort=semver)](https://github.com/ccjjxx99/Macast-RTX-Edition/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/ccjjxx99/Macast-RTX-Edition/total)](https://github.com/ccjjxx99/Macast-RTX-Edition/releases)
[![Build Windows](https://github.com/ccjjxx99/Macast-RTX-Edition/actions/workflows/build-windows.yml/badge.svg)](https://github.com/ccjjxx99/Macast-RTX-Edition/actions/workflows/build-windows.yml)
[![GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-76b900)](LICENSE)
[![mpv 0.41.0](https://img.shields.io/badge/mpv-0.41.0-76b900)](https://github.com/mpv-player/mpv/releases/tag/v0.41.0)

Macast RTX Edition 是一款面向 Windows 的轻量级 DLNA/UPnP 媒体接收器。它让电脑出现在局域网的投放设备列表中，接收来自手机、平板、电脑、家庭服务器及其他 DLNA 控制端的视频、音乐和图片，并交给内置的 mpv 播放。

程序常驻系统托盘，不需要媒体库、账号或内容服务。支持 NVIDIA RTX 的电脑还可以直接启用 RTX Video Super Resolution 和 RTX Video HDR。

[下载最新版](https://github.com/ccjjxx99/Macast-RTX-Edition/releases/latest) · [查看源码](https://github.com/ccjjxx99/Macast-RTX-Edition) · [报告问题](https://github.com/ccjjxx99/Macast-RTX-Edition/issues) · [安全策略](SECURITY.md)

## ✨ 核心功能

### 📡 DLNA 媒体接收

- 在局域网中注册为标准 DLNA/UPnP Media Renderer。
- 接收常见 DLNA 控制端发送的网络视频、音频、图片及本地媒体地址。
- 支持播放、暂停、停止、音量调节和进度跳转等远程控制指令。
- 电脑根据收到的地址读取媒体，不需要逐帧镜像控制端屏幕；如果控制端同时提供文件或代理服务，它仍需保持在线。

### 🎬 mpv 播放内核

- 内置 mpv `0.41.0` 官方 Windows 64 位版本。
- 支持硬件解码、全屏、窗口置顶和播放位置记忆。
- 可以设置窗口尺寸与屏幕位置。
- 可从托盘菜单复制当前媒体地址，方便调试或交给其他播放器。
- 支持用户自己的 mpv 配置和脚本。

### 🟢 NVIDIA RTX Video

- RTX Video Super Resolution（VSR）与 RTX Video HDR 可以分别开关。
- VSR 根据视频尺寸和播放窗口自动计算放大倍率，只在视频确实被放大时启用。
- 默认处理最高 1440p 的输入，放大倍率限制在 `1.05x`～`4x`。
- 使用 `gpu-next`、D3D11、`d3d11va` 和 `d3d11vpp` 接入 NVIDIA 视频处理链路。
- 原生 HDR 视频不会再次执行 SDR 转 HDR。

### 🧩 托盘与本地设置

- 启停 DLNA 服务、开机启动和自动检查更新。
- 切换 Renderer、Protocol、硬件解码、窗口大小、窗口位置与置顶状态。
- 本地设置页可查看组件信息、编辑高级配置和读取运行日志。
- 无框架设置页面，全部资源随程序本地提供，不依赖 CDN。

## 🔄 工作方式

```mermaid
flowchart LR
    A["DLNA 控制端<br/>手机、平板、电脑、家庭服务器"] -->|媒体地址与播放指令| B["Macast RTX Edition"]
    B --> C["mpv 0.41.0"]
    C --> D["硬件解码与 RTX Video"]
    D --> E["Windows 显示器或音频设备"]
```

Macast RTX Edition 是接收端，不是屏幕镜像工具。控制端发送媒体地址和播放指令，电脑负责连接媒体服务器并完成解码、渲染和声音输出。

## 🚀 安装

1. 打开 [Releases](https://github.com/ccjjxx99/Macast-RTX-Edition/releases/latest)，下载最新的 `Macast-RTX-Edition-v*.exe`。
2. 运行程序。Windows 防火墙首次询问时，允许它访问专用网络。
3. 确保控制端和电脑处于同一局域网。
4. 在 DLNA 控制端的设备列表中选择名称带有 `Macast RTX` 的设备。
5. 播放窗口会在收到媒体后自动打开，其他选项可在系统托盘中调整。

程序是单文件版本，无需安装。退出程序后不会继续提供 DLNA 接收服务。

## 🟢 RTX 设置

RTX VSR 默认开启，RTX Video HDR 默认关闭。普通显卡或核显也能使用 DLNA 接收和 mpv 播放，只需在托盘菜单中关闭 RTX 选项。

启用 RTX 功能需要：

- Windows 10/11 64 位；
- NVIDIA GeForce RTX 显卡和较新的 Game Ready 或 Studio 驱动；
- RTX Video HDR 需要 HDR 显示器，并在 Windows 显示设置中打开 HDR；
- 播放内容需要满足 NVIDIA 驱动的 RTX Video 处理条件。

可以在 NVIDIA App 的“系统 → 视频”页面查看 VSR 和 HDR 是否处于活动状态。功能未激活时，先确认播放窗口正在放大视频、mpv 使用的是 NVIDIA 显卡，并检查驱动中的视频增强开关。

## ⚙️ 设置与数据

托盘菜单中的 `Advanced Setting` 会打开本机设置页。页面和相关 API 仅接受来自 `127.0.0.1` 或 `::1` 的请求。

Windows 配置目录：

```text
%LOCALAPPDATA%\ccjjxx99\Macast-RTX-Edition
```

该目录保存高级设置、用户脚本和运行日志。自定义 Renderer、Protocol 或 mpv 脚本会以当前用户权限运行，只应加载自己信任的代码。

## 🔒 安全与隐私

- 不需要账号，不上传媒体库或播放记录。
- 管理接口仅限本机访问，并使用 CSRF 校验。
- 局域网输入的 XML 禁止实体解析、DTD 和外部网络访问。
- UPnP 事件回调被限制到发起订阅的设备地址。
- 构建流程固定 GitHub Actions 提交和 mpv 下载校验值。
- Python 依赖由 `pip-audit` 在每次 GitHub Actions 构建时检查。

投放时，电脑需要直接访问控制端提供的媒体地址。地址、请求权限或网络路由不可用时，播放器可能无法打开内容；部分媒体服务器也会限制进度跳转或临时链接的有效时间。

## 常见问题

<details>
<summary>设备列表中找不到 Macast RTX Edition</summary>

- 确认程序仍在系统托盘运行。
- 将 Windows 网络类型设为“专用网络”，并允许程序通过专用网络防火墙。
- 确认两台设备处于同一局域网，且路由器没有开启 AP 隔离、客户端隔离或访客网络。
- VPN、多网卡和虚拟网卡可能影响 SSDP 广播，可暂时切换到实际使用的局域网接口排查。

</details>

<details>
<summary>视频能播放，但不能拖动进度</summary>

进度跳转需要媒体服务器、传输协议和控制端共同支持。可以先用 mpv 键盘快捷键测试，再更换媒体地址或线路。直播流、临时代理地址以及缺少时间索引的媒体可能无法跳转。

</details>

<details>
<summary>RTX VSR 或 HDR 没有激活</summary>

确认 NVIDIA App 已打开对应功能。VSR 只在视频发生放大时启用；HDR 还需要 Windows HDR 已开启。笔记本用户应确认播放进程运行在 NVIDIA 独立显卡上。

</details>

## 🧰 从源码构建

Windows 构建推荐使用 Python 3.12。脚本不会覆盖已经存在的输出目录；重复构建时请指定新的 `OutputRoot`。

```powershell
py -3.12 -m venv .venv-rtx
.\.venv-rtx\Scripts\python.exe -m pip install -r requirements\build-windows.txt
.\scripts\build_windows.ps1 -Python .\.venv-rtx\Scripts\python.exe
```

默认产物：

```text
.build\windows-v1.0.1\dist\Macast-RTX-Edition-v1.0.1.exe
.build\windows-v1.0.1\dist\SHA256SUMS.txt
```

构建脚本下载官方 mpv `0.41.0` Windows MSVC 包，并核对固定的 SHA-256：

```text
4E197F729F5071C6772F35FFFD96E0F36E3E8A044BD9479B136BB09B7C6A80FF
```

手动执行依赖审计：

```powershell
.\.venv-rtx\Scripts\python.exe -m pip_audit -r requirements\windows.txt
```

GitHub Actions 会在提交和 Pull Request 上执行依赖审计与 Windows 构建。推送符合 `v*.*.*` 格式的标签时，工作流会创建 Release 并上传 EXE 与 `SHA256SUMS.txt`。

## 参与项目

Bug、兼容性报告和功能建议可以提交到 [Issues](https://github.com/ccjjxx99/Macast-RTX-Edition/issues)。提交问题时，请尽量附上 Windows 版本、显卡与驱动版本、控制端类型、媒体协议以及相关日志。

Pull Request 请保持改动范围清晰，并说明实际验证条件。涉及播放器、DLNA 协议或 RTX 处理链路的修改，建议同时提供可复现的媒体样例或日志。

## 许可证与致谢

Macast RTX Edition 基于 [xfangfang/Macast](https://github.com/xfangfang/Macast) 开发，继续使用 [GNU GPL v3 或更高版本](LICENSE)。发布二进制时，对应源码也会保留在本仓库。

mpv、FFmpeg、libplacebo 等组件使用各自的许可证。来源、版本与再分发说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

> 本项目只负责接收和播放媒体，不提供内容、媒体索引或解析服务。请确认所访问内容及其来源符合当地法律和服务条款。
