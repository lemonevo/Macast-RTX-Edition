# plugins —— 本仓库的插件源

设置页「插件」标签默认从这个目录的 [`info.json`](info.json) 拉取插件清单，安装的插件文件也来自这里（`raw.githubusercontent.com` 上的本仓库文件）。这样每个插件都可以在本仓库内单独打补丁，不必再依赖上游。

| 插件 | 类型 | 平台 | 来源 | 说明 |
| --- | --- | --- | --- | --- |
| 哔哩哔哩投屏（Bilibili 投屏）`nirvana.py` | Protocol | darwin, win32, linux | 上游 + **本地修复** | B 站客户端里显示为「我的小电视(有弹幕)」，支持弹幕、倍速、自动下集、1080P |
| IINA Renderer `iina.py` | Renderer | darwin | 上游镜像 | 用 IINA 播放（IINA 基于 mpv，体验接近内置 mpv） |
| Web Renderer `web.py` | Renderer | darwin, linux, win32 | 上游镜像 | 用浏览器接收媒体地址（下载文件、播放 m3u8） |
| PotPlayer Renderer `potplayer.py` | Renderer | win32 | 上游镜像 | 用 PotPlayer 播放，只支持播放/停止 |
| Live Renderer `live.py` | Renderer | win32, darwin, linux | 上游镜像 | 基于 MPVRenderer 的直播支持 |
| PIFMRDS Renderer `pi_fm.py` | Renderer | linux | 上游镜像 | 树莓派 FM 发射，仅适合树莓派 |

> 「上游镜像」= 与 [xfangfang/Macast-plugins](https://github.com/xfangfang/Macast-plugins) 内容一致，只改了下载地址，方便在本仓库统一分发。
> 从设置页安装插件时，除了本仓库，**上游插件仓库的地址也仍然被允许**（便于回退安装上游版本）。

> ⚠️ 如果这些文件还没有 push 到 GitHub，设置页会**回退使用上游清单**（列表里 B 站插件显示为上游的 `NVA Protocol`，而不是本仓库的 v0.34）。这时不要从设置页重装该插件 —— 那会用上游原版覆盖本地修复版；请先 push 本仓库，或重装后用 `plugins/nirvana.py` 覆盖回去。

## 哔哩哔哩投屏（Bilibili 投屏）

上游文件：`nirvana/nirvana.py`（作者 [xfangfang](https://github.com/xfangfang)），上游版本 `0.33`，本副本版本 `0.34`。
原名 `NVA Protocol`，2026-09 起改名为 **哔哩哔哩投屏（Bilibili 投屏）**，配置项 `Macast_Protocol` 会跟着变。

本副本修复的问题（上游 issue [#22](https://github.com/xfangfang/Macast-plugins/issues/22) 报告过弹幕开关问题，其余尚无修复）：

| # | 问题 | 处理 |
| --- | --- | --- |
| 1 | `SwitchDanmaku` 只改渲染层，协议层状态不同步，下一次投屏又按旧状态把弹幕关掉（表现为"有的视频没弹幕"） | 新增 `set_danmaku_visibility()`，渲染层与协议层一起更新 |
| 2 | 弹幕文件固定为 `macast.ass`，切集/切画质时重复下载互相覆盖 | 按 cid 命名：`macast-danmaku-<cid>.ass`，同一 cid 复用 |
| 3 | 空文本、时间戳非法、字段不足的弹幕会让排序/解析抛异常，整份 ASS 生成失败后仍 `sub-add` 空文件 | 逐条容错丢弃脏数据，失败时提示"弹幕加载失败"/"该视频暂无弹幕" |
| 4 | `Dialogue` 行的 Name 字段使用的是未转义的弹幕文本，含逗号的弹幕会破坏 ASS 字段 | Name 字段改用弹幕 id，并对文本里的 `\ { }` 做转义 |
| 5 | `support_formats` 缺失时 `supportQnList` 为空，App 里没有画质菜单 | 用 `accept_quality` + `accept_description` 兜底生成 |
| 6 | 请求的画质被 B 站限制（未登录/非大会员）时静默回退 | 明确提示"已切换到 720P，更高画质需要登录 B 站账号 / 需要大会员" |
| 7 | `dash` 分支盲取 `video[0]`；`durl`/`dash`/`live_mobile` 字段缺失时 `KeyError` 打断播放 | 按目标画质选轨，字段改用 `.get()` |
| 8 | 出问题只能看 `macast.log` 里的引擎日志 | 新增插件日志 `nva-plugin.log`（记录画质决策、弹幕结果、异常） |
| 9 | **1080P 点不出来**：B 站只通过 DASH 提供高画质，而插件请求的是 FLV 合并流（实测上限 720P，`quality=64`） | 优先请求 DASH（`fnval=16`）并按目标画质选轨，音轨用 `audio-add` 单独挂载；渲染器不支持外挂音轨或缺少音轨时回退合并流 |
| 9b | 切到 1080P 后**没有声音** / **切换分辨率后弹幕消失**：DASH 音视频分离，而 mpv 在 `loadfile` 替换文件期间会拒绝 `audio-add` 与 `sub-add`（实测返回 `error running command`） | `MPVRenderer` 把"挂音轨/挂字幕"都延后到 mpv 的 `file-loaded` 事件（文件已就绪时立即执行），并保留 2 秒兜底定时器 |
| 10 | 客户端把画质/倍速传成字符串（`'80'`），导致选轨失败、倍速 UI 不更新；`float('')` 还会中断播放流程 | 参数统一 `int/float` 转换并容错；切换倍速后回传 `SpeedChanged`；所有异常改为带 traceback 记录 |

## 安装

设置页「插件」标签 → 选择插件 → 「安装」（安装后 Macast 会自动重启加载）。也可以手动把 `.py` 复制到配置目录的 `renderer/` 或 `protocol/`，然后重启 Macast：

| 系统 | 配置目录 |
| --- | --- |
| Windows | `%LOCALAPPDATA%\ccjjxx99\Macast-RTX-Edition\` |
| macOS | `~/Library/Application Support/Macast-RTX-Edition/` |
| Linux | `~/.config/Macast-RTX-Edition/` |

macOS / Linux：

```sh
cp plugins/nirvana.py "$HOME/Library/Application Support/Macast-RTX-Edition/protocol/"
# Linux 使用 ~/.config/Macast-RTX-Edition/protocol/
```

Windows（PowerShell）：

```powershell
Copy-Item plugins\nirvana.py "$env:LOCALAPPDATA\ccjjxx99\Macast-RTX-Edition\protocol\"
```

复制后重启 Macast，并在托盘菜单 `Setting → Protocols` 里选择 **哔哩哔哩投屏（Bilibili 投屏）**。

## 排查（哔哩哔哩投屏）

日志：`<配置目录>/nva-plugin.log`

- 画质：`画质降级: 请求 X -> 实际 Y`、`SwitchQn 参数无效: {...}`、`使用 DASH 流 qn=... 音轨=有/无`；
- 弹幕：`挂载弹幕 /path (N bytes)`、`该视频暂无弹幕`、`弹幕生成失败 cid=...`；
- 音轨/字幕挂载分别在 mpv 报告 `file-loaded` 之后（`挂载外挂音轨: ...`、`挂载字幕: ...`）；
- 高画质依赖：① DASH 取流（本地已默认启用）；② 登录态（B 站客户端会随投屏命令传 `accessKey`）。番剧未登录时 B 站不返回 DASH，只能用合并流；
- 1080P 高码率（qn=112）需要大会员，属于 B 站账号权限，插件无法绕过。

## 许可

这些插件的作者是 [xfangfang](https://github.com/xfangfang)（`live.py` 的作者是 dushan555），上游声明"仅用于编程学习使用，禁止用做商业用途"。本目录保留各文件的原始版权头与来源链接；如果要再分发或商用，请先与原作者确认。其余见仓库根目录 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。
