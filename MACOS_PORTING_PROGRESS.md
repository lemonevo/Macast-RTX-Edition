# Macast RTX Edition：macOS 兼容开发进度

## 当前状态

项目基于 `ccjjxx99/Macast-RTX-Edition`，版本为 `1.1.1`，目前已经可以在 macOS（本机 Apple M4）上源码安装并启动。

核心验证已经通过：

- 菜单栏 GUI 可以启动；
- Macast 不在 Dock 中显示无用的应用图标；
- mpv 0.41.0 可以正常启动；
- mpv IPC socket 可以正常连接；
- DLNA/UPnP 服务可以启动；
- `/description.xml` 返回正常；
- 本地高级设置页面返回 HTTP 200；
- Apple Silicon 不会错误进入 Windows RTX Video 处理路径；
- 程序可以正常退出。

## 已完成的修改

### 1. macOS/Linux 跳过 RTX 启动提示

文件：`macast_renderer/mpv.py`

RTX Video 只适用于 Windows/NVIDIA。macOS 和 Linux 使用普通 mpv 播放路径，不再显示“RTX 不可用”的启动提示。

### 2. macOS 默认视频窗口优化

文件：`macast_renderer/mpv.py`

- macOS 默认播放窗口位置改为屏幕中央；
- 默认大小改为 `Large`，约占屏幕 40%；
- 已将当前配置设置为居中和大窗口：

```json
{
  "PlayerPosition": 4,
  "PlayerSize": 2
}
```

配置文件位置：

```text
~/Library/Application Support/Macast-RTX-Edition/macast_setting.json
```

### 3. macOS 菜单栏应用模式

文件：`macast/gui.py`

使用 macOS `NSApplicationActivationPolicyAccessory`，启动后只显示菜单栏图标，不在 Dock 中显示 Macast 图标。

### 4. 修复安装后的命令入口

文件：`pyproject.toml`、`macast/macast.py`

新增并修复以下命令：

```text
macast-rtx-gui
macast-rtx-cli
```

入口现在位于正式 Python 包内，不再依赖仓库根目录的 `Macast.py`，解决了：

```text
ModuleNotFoundError: No module named 'Macast'
```

### 5. 修复中文本地化加载

文件：`macast/macast.py`、`Macast.py`、`pyproject.toml`

原问题是安装后的启动入口绕过了原版 `Macast.py` 的语言初始化，导致菜单变成英文。现在启动入口会根据 macOS 系统语言加载 gettext 翻译。

中文翻译文件来源：`i18n/zh_CN/LC_MESSAGES/macast.po`

已经验证：

- `Setting` → `设置`；
- `Player Position` → `播放器位置`。

## 本地开发环境

虚拟环境：

```text
.venv-macos
```

安装/启动：

```bash
cd ~/Desktop/Macast-RTX-Edition
source .venv-macos/bin/activate
macast-rtx-gui
```

本机通过 Homebrew 安装了 mpv：

```text
mpv 0.41.0
```

## 当前已知问题

1. 还没有制作 macOS `.app`/`.dmg` 安装包，目前是源码 + 虚拟环境运行。
2. 手机实际投屏播放流程还需要继续做完整验证。
3. GitHub 更新检查偶尔会遇到 API `403 rate limit exceeded`，不影响投屏功能。
4. `rumps` 仍可能打印 macOS 的 quit button 警告，不影响运行。
5. 设置页面部分说明仍然偏向 Windows/RTX，需要改成跨平台文案。
6. Macast-plugins 的安装和 macOS 兼容性还没有完整验证。

## 建议的下一步

1. 使用手机投屏测试视频、音频、图片、暂停、拖动进度和音量控制。
2. 修复或隐藏设置页面中仅适用于 Windows 的 RTX 说明。
3. 检查 macOS 多网卡/虚拟网卡下的设备发现问题。
4. 增加 macOS 构建脚本，制作 `.app`。
5. 决定是否保留在线插件安装，或改成手动插件目录管理。
6. 在 macOS 上补充自动化测试，并持续验证后续版本。
