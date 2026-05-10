# BabySentinel

婴儿实时监控系统，整合 **Sense-U 智能睡眠监测仪**（蓝牙传感器）与 **Tapo 摄像头**，提供 Web 监控界面、育儿日志、Bark/Discord 告警和录像回放。

支持 **Windows 10/11** 和 **macOS（Intel / Apple Silicon）**。

---

## 功能

- **实时传感器监控**：呼吸频率、衣内温度、睡姿（仰/俯/左/右/坐姿）、电量
- **摄像头直播**：通过 go2rtc 将 RTSP 流转为 WebRTC，浏览器延迟 < 1 秒
- **告警推送**：俯卧持续告警、呼吸停止告警、喂奶提醒，并发推送到 **Bark（iOS）** 和 **Discord**
- **育儿日志**：记录喂奶、换尿布、睡眠、洗澡、体温/身高/体重等事件，按日统计；存储后端为 **SQLite**
- **录像回放**：5 分钟一段连续录像，回放时同步显示对应时刻的传感器数据
- **服务管理**：独立 Web 界面，可单独启停各微服务，支持手机响应式布局
- **多客户端**：传感器状态通过 WebSocket 实时推送给所有连接的浏览器

---

## 系统架构

```
Mac / Linux 主机                                    Pi (推荐)
┌─────────────────────────────────────────────┐    ┌────────────────────────┐
│ manager.py (9091)                            │    │ sense-u-ble :8082      │
│ ├── go2rtc                                   │    │   独立 repo，systemd   │
│ ├── services/web/server.py (8080)            │    │   --user 单元自启      │
│ │     ↑ 接收 sensor/alert push (POST)        │←───┤   推送 BLE 数据回主机  │
│ └── services/recorder/service.py             │    │                        │
│                                              │    │  https://github.com/    │
│ services/voice/voice_service.py (8001)       │    │  mao-mao-yu/sense-u-ble │
│   POST /voice/process  WAV→WAV               │    └────────────────────────┘
└─────────────────────────────────────────────┘
```

**BLE 服务 (Sense-U Baby Pro 接入)** 已抽离为独立 repo [`sense-u-ble`](https://github.com/mao-mao-yu/sense-u-ble) 跑在 Raspberry Pi 上，通过 HTTP 把传感器数据 / 告警事件推回到这个主机的 `/api/internal/sensor`。Manager UI 里的 BLE 卡片通过 SSH 控制 Pi 上的 systemd unit 启停 + 自检 git 更新。

各服务配置**分而治之**：
- 根目录 `config.json` —— 跨服务字段（端口、宝宝信息、RTSP、推送凭据、语言、`pi_host`）
- `services/{recorder,voice,web}/config.json` —— 各服务自己的内部参数
- 启动时各服务先读自己的 service config，再 fallback 到 root config

各服务**独立进程**，通过 HTTP 和文件互相通信。manager 维护服务生命周期：
- 启动时扫描并清理上次未退干净的孤儿子进程
- 子进程崩溃自动重启
- 自身退出时通过 lifespan shutdown + atexit 兜底，确保子进程组被整组干掉

---

## 准备工作

### 硬件

- **Sense-U 婴儿监测仪**（Baby Pro 等贴片式睡眠传感器）
- **Tapo 摄像头**（支持 RTSP 的型号，如 C100/C200/C210/C310）
- 主机需支持 **蓝牙 4.0+（BLE）**

### 软件

- Python **3.11+**
- ffmpeg（录像功能需要，安装脚本可自动下载到 `bin/`）
- go2rtc（摄像头直播需要，安装脚本可自动下载到 `bin/`）

---

## 安装

### Windows

```powershell
.\setup.ps1
```

### macOS

```bash
bash setup.sh
```

安装脚本会自动完成：

1. 检查 Python 3.11+
2. 创建虚拟环境 `venv/`
3. 安装 Python 依赖（`requirements.txt`）
4. 下载 go2rtc 二进制到 `bin/`
5. 检查 / 下载 ffmpeg 到 `bin/`（macOS 自动下 arm64 / x86_64 对应版本）
6. 从根 `config.example.json` 复制初始 `config.json`
7. 创建 `logs/` 和 `recordings/` 目录

> **per-service 配置**：`services/{ble,recorder,voice,web}/config.json` **不需要手动 copy**——各服务首次启动时 `load_service_config()` 会自动从同目录的 `config.example.json` 生成。要改服务内部参数时直接编辑生成出的那份即可。

---

## 配置

配置分两层：

- **根 `config.json`** —— 跨服务字段（端口、宝宝信息、RTSP、推送凭据、语言、`pi_host`）
- **`services/{recorder,voice,web}/config.json`** —— 各服务自己的内部参数

> 安装脚本会从对应的 `config.example.json` 复制初始模板。不存在的字段自动从 example 兜底，新版本加字段时旧配置不会失效。

**最小必填**（根 `config.json`）：

```jsonc
{
  "tapo_rtsp": "rtsp://user:pass@192.168.1.x:554/stream1",
  "baby": { "birth_date": "20240101", "feed_interval_min": 150 },

  // BLE 跑在 Pi，配 SSH 三件套让 manager UI 能控制 Pi 服务
  "pi_host":     "192.168.0.20",
  "pi_ssh_user": "pi",
  "pi_ssh_key":  "~/.ssh/pi_key"
}
```

> BLE (Sense-U Baby Pro) 部署在 Pi 上的 [`sense-u-ble`](https://github.com/mao-mao-yu/sense-u-ble) repo，配置在 Pi 的 `~/sense-u-ble/config.json` 里——见该 repo README。本机 manager 通过 SSH 远程控制启停 + git 自检。

### 根 `config.json` 字段

#### 连接 / 媒体

| 字段 | 默认 | 说明 |
|---|---|---|
| `tapo_rtsp` | — | 摄像头 RTSP 地址（含密码） |
| `ffmpeg_path` | `""` | ffmpeg 路径，留空自动从 `bin/` 或系统 PATH 查找 |
| `go2rtc_path` | `""` | go2rtc 路径，同上 |
| `segment_s` | `180` | 视频分段时长（秒），默认 3 分钟一段 |

> 传感器数据写入与 `ble_poll_interval_s` 同频率，每次成功 BLE 轮询都落入 SQLite (`logs/sensors.db`)。

#### 端口

| 字段 | 默认 | 说明 |
|---|---|---|
| `web_port` | `8080` | 监控主界面端口 |
| `go2rtc_port` | `1984` | go2rtc WebRTC 端口 |
| `ble_port` | `8082` | BLE 传感器微服务端口 |
| `voice_service_port` | `8001` | 语音服务端口 |
| `manager_port` | `9091` | 管理界面端口 |

#### BLE 时序（跨服务契约）

| 字段 | 默认 | 说明 |
|---|---|---|
| `ble_poll_interval_s` | `2` | 0xBA 数据 polling 间隔（秒），ble + recorder 都消费 |
| `ble_health_timeout_s` | `10` | web 监测 ble_service 心跳超时（秒），超时即标 `ble_ok=false` |

#### 通知凭据

支持 Discord 和 Bark 两个独立通道，**可同时配置**，告警会并发推送到所有已配置的渠道。

| 字段 | 默认 | 说明 |
|---|---|---|
| `discord_token` | `""` | Discord Bot Token（留空跳过 Discord） |
| `discord_channel_ids` | `[]` | 接收告警的频道 ID 列表 |
| `discord_user_ids` | `[]` | 接收告警私信的用户 ID 列表 |
| `bark_server_url` | `https://api.day.app` | Bark 服务器地址（官方 / 自建） |
| `bark_keys` | `[]` | Bark device key 数组，**支持多个 iOS 设备** |

详见后面的 [Bark 通知配置](#bark-通知配置) 和 [Discord 告警配置](#discord-告警配置)。

#### 其他

| 字段 | 默认 | 说明 |
|---|---|---|
| `log_level` | `INFO` | 日志级别：`DEBUG` / `INFO` / `WARNING` |
| `language` | `ja` | UI / 通知语言：`ja` / `zh` |
| `baby.name` | `赤ちゃん` | 宝宝名字（喂奶提醒里使用） |
| `baby.birth_date` | `""` | 宝宝生日 `YYYYMMDD` 或 `YYYY-MM-DD`，用于计算日龄 + 推荐奶量 |
| `baby.weight_g` | `0` | 体重（克） |
| `baby.feed_type` | `formula` | `formula`（配方奶）或 `breastfeed`（母乳） |
| `baby.feed_interval_min` | `150` | 喂奶间隔提醒（分钟） |

### BLE (Sense-U Baby Pro) 配置 → 在 Pi 上的 [`sense-u-ble`](https://github.com/mao-mao-yu/sense-u-ble) repo

BLE 服务和所有相关配置（`ble_address` / `ble_mac` / 告警阈值 / 配对工具）都迁到了独立 repo。在 Pi 上：

```bash
git clone https://github.com/mao-mao-yu/sense-u-ble.git ~/sense-u-ble
cd ~/sense-u-ble
python -m venv venv && ./venv/bin/pip install -e .
cp config.example.json config.json   # 填 ble_address + consumer_url 指向 Mac
./venv/bin/python tools/pairing.py    # 一次性获取 baby_code.json
systemctl --user enable --now sense-u-ble.service
loginctl enable-linger $USER          # 重启自动起，无需登录
```

详细参数 + systemd unit 模板见该 repo 的 README。

### `services/recorder/config.json`（录像服务）

| 字段 | 默认 | 说明 |
|---|---|---|
| `sensor_interval_s` | `5` | 录像期间传感器时序写入 SQLite 的间隔（秒） |

### `services/web/config.json`（Web 服务）

| 字段 | 默认 | 说明 |
|---|---|---|
| `web_host` | `0.0.0.0` | Web 服务监听地址，`0.0.0.0` 允许局域网访问 |
| `feed_repeat_s` | `1800` | 喂奶到点后每隔多久重复提醒（秒） |

`services/voice/config.json` 见下方 [语音助手](#语音助手) 章节。

#### 通知推送

支持 Discord 和 Bark 两个独立通道，**可同时配置**，告警会并发推送到所有已配置的渠道。

| 字段 | 默认 | 说明 |
|---|---|---|
| `discord_token` | `""` | Discord Bot Token（留空跳过 Discord） |
| `discord_channel_ids` | `[]` | 接收告警的频道 ID 列表 |
| `discord_user_ids` | `[]` | 接收告警私信的用户 ID 列表 |
| `bark_server_url` | `https://api.day.app` | Bark 服务器地址（官方 / 自建） |
| `bark_keys` | `[]` | Bark device key 数组，**支持多个 iOS 设备** |

详见后面的 [Bark 通知配置](#bark-通知配置) 和 [Discord 告警配置](#discord-告警配置)。

#### 其他

| 字段 | 默认 | 说明 |
|---|---|---|
| `log_level` | `INFO` | 日志级别：`DEBUG` / `INFO` / `WARNING` |
| `baby.birth_date` | `""` | 宝宝生日 `YYYYMMDD`，用于计算日龄 + 推荐奶量 |
| `baby.weight_g` | `0` | 体重（克） |
| `baby.feed_type` | `formula` | `formula`（配方奶）或 `breastfeed`（母乳） |
| `baby.feed_interval_min` | `150` | 喂奶间隔提醒（分钟） |

> `config.json` 没填写的字段会自动从 `config.example.json` 兜底。新版本加字段时旧配置不会失效。

### Sense-U 设备扫描 + 配对（在 Pi 上）

```bash
# 在 Pi 上的 sense-u-ble repo 里
./venv/bin/python tools/scan.py        # 列出附近 BLE 设备，找 Sense-U Baby Pro
./venv/bin/python tools/pairing.py     # 一次性配对，写出 baby_code.json
```

`baby_code.json` 跨设备通用——如果你之前在另一台机器配对过，直接 `scp` 过来到 Pi 的 sense-u-ble 目录即可。

---

## 启动

### 推荐：通过管理器统一启动

```bash
# Windows
.\venv\Scripts\python.exe manager.py

# macOS
./venv/bin/python manager.py
```

打开管理界面：**http://localhost:9091**

manager 会按顺序启动：go2rtc → server → recorder → voice。BLE service 跑在 Pi 上的 sense-u-ble，manager UI 通过 SSH 远程控制（启停、日志、git 自检更新）。

### 单独启动各服务（调试用）

```bash
./venv/bin/python services/web/server.py           # 仅主 Web 服务（含 Discord Bot）
./venv/bin/python services/recorder/service.py     # 仅录像
./venv/bin/python services/voice/voice_service.py  # 语音服务
# BLE: 在 Pi 上 systemctl --user start sense-u-ble.service
```

---

## 使用界面

### 监控主界面 — http://localhost:8080

- 实时传感器（呼吸 / 衣内温度 / 姿势 / 电量 / 连接状态）
- 摄像头 WebRTC 直播
- 育儿日志（喂奶 / 尿布 / 睡眠等），日期可前后切换
- 告警历史

### 录像回放 — http://localhost:8080/playback

- 按日期浏览历史录像
- 5 分钟一段视频片段（默认值，由 `segment_s` 决定）
- 视频播放时同步显示对应时刻的传感器数据
- 自动切到下一段

### 服务管理 — http://localhost:9091

- 查看各服务状态（running / stopped / crashed）
- 单独启动 / 停止 / 重启
- 实时查看每个服务的日志输出
- **手机响应式**：< 768px 切换为单列纵向滚动布局

---

## Bark 通知配置（推荐 iOS）

[Bark](https://bark.day.app/) 是一个免费的 iOS 推送 App，跟 Discord 不同，支持**关键告警**（绕过静音/勿扰、最大音量持续响铃）。

1. 在 iPhone App Store 装 [Bark](https://apps.apple.com/app/bark/id1403753865)
2. 打开 App 拿到你的 device key（一串约 22 个字符）
3. 填进 `config.json`：

```json
"bark_server_url": "https://api.day.app",
"bark_keys": [
  "your_device_key_here",
  "another_device_key_for_partner"
]
```

支持任意多个设备 key，告警会同时推送到所有 iOS。

### 各告警级别行为

| 级别 | 触发场景 | iOS 行为 |
|---|---|---|
| `danger` | 俯卧持续超时、呼吸停止 | **关键告警**：绕过静音/勿扰，最大音量 + 持续响铃直到点开，自动入历史 |
| `warning` | 喂奶提醒 | 普通通知，亮屏一次，遵循系统铃声/静音设置 |
| `info` | 一般信息 | 静默通知，仅出现在通知中心 |

> **关键告警必须授权两次**：① Bark App 内打开「关键警告」开关；② iOS 系统设置 → 通知 → Bark → 启用「关键警告」。第一次发 critical 推送时 iOS 会弹窗，必须点允许。

---

## Discord 告警配置（可选）

跟 Bark 并列工作，配置任一即可，配置两个则双重推送。

1. 在 [Discord Developer Portal](https://discord.com/developers/applications) 创建 Bot 拿 Token
2. 把 Bot 拉进你的服务器，拿目标频道 ID
3. 填 `config.json`：

```json
"discord_token": "your-bot-token",
"discord_channel_ids": [123456789012345678],
"discord_user_ids": []
```

Discord Bot 提供两个 Slash command：

| 命令 | 作用 |
|---|---|
| `/get_sensor_status_now` | 查看传感器实时状态（呼吸 / 衣内温度 / 姿势 / 电量 / BLE 连接） |
| `/get_status_today` | 查看今天的育儿记录（概览 + 时间线明细） |

启动 server 时自动注册 / 覆盖命令；旧的 `/get_babystatus` 会被自动下线。

---

## Pi 麦克风音频接入（替代 Tapo 内置麦）

> ⚠️ **实测告警（2026-05）**：用 **ReSpeaker 4-Mic Array (UAC1.0)** + Pi 4 实测，静室里硬件底噪明显（c0 通道 RMS -42 dB，是 firmware AGC 在静音时拉满放大模拟前端噪声所致）。换 USB 线、换 Pi 端口、`afftdn` 频谱降噪（产生 musical noise）、`agate` noise gate 等组合都未能得到自然听感。Tapo 内置麦虽是 8kHz pcm_alaw 音质有限，但 baseline 干净不烦人。
> 
> **结论**：当前不推荐 ReSpeaker UAC1.0 走这条链路。如果你想再试，建议换 **带 XMOS VocalFusion DSP 固件的 ReSpeaker（如 USB Mic Array v2.0）**——它的 firmware 会做 NS/AGC 处理，c0 输出已经是降噪后的语音通道。或换其它带本地 DSP 的 USB mic。
> 
> 下面整套部署方案保留为**有效参考**，代码（`scripts/pi_streamer.sh` + `manager._gen_go2rtc_yaml` 多源逻辑）也都还在；只要 `pi_audio_rtsp` 不为空就会走多源，留空就 fallback 到 Tapo 单源。

如果你在 Pi 上接了 ReSpeaker 等 USB 麦克风（音质比 Tapo 内置麦好得多），可以让监控页同时显示 Tapo 视频 + Pi 麦音频，端到端延迟在 100~200ms。

### 工作原理

```
ReSpeaker → Pi ALSA → ffmpeg(libopus 32k) → mediamtx RTSP → 服务端 go2rtc
                                                              ↑
                                              Tapo RTSP ──────┤   多源轨道路由
                                                              ↓     (无转码)
                                                          baby 流 → 浏览器 WebRTC
```

服务端 go2rtc 用**多源轨道路由**直接合并两路 RTP，不经 ffmpeg 转码。比"服务端再起一个 ffmpeg 做 remux"的方案少 50~150ms 延迟。

### Pi 端准备

1. 装 ffmpeg + mediamtx：

   ```bash
   sudo apt install ffmpeg
   # 从 https://github.com/bluenviron/mediamtx/releases 下载对应架构二进制
   # 假设放在 ~/mediamtx/
   ```

2. 写最小 `mediamtx.yml`（只允许 publisher 推流到 `respeaker` 路径）：

   ```yaml
   paths:
     respeaker:
       source: publisher
   ```

3. 找到 ReSpeaker 的 ALSA 设备号：

   ```bash
   arecord -l
   # 比如显示 card 1: ArrayUAC10 ...  → 设备名 plughw:1,0
   ```

4. 启动 mediamtx 和 streamer（两个终端）：

   ```bash
   ~/mediamtx/mediamtx ~/mediamtx/mediamtx.yml
   bash scripts/pi_streamer.sh plughw:1,0
   ```

   或者用 **systemd user 服务**（实测推荐，**无需 sudo**）：

   ```bash
   mkdir -p ~/.config/systemd/user

   cat > ~/.config/systemd/user/mediamtx.service <<'UNIT'
   [Unit]
   Description=mediamtx RTSP server (BabySentinel)
   After=network-online.target
   Wants=network-online.target

   [Service]
   Type=simple
   ExecStart=%h/mediamtx/mediamtx %h/mediamtx/mediamtx.yml
   Restart=always
   RestartSec=3

   [Install]
   WantedBy=default.target
   UNIT

   cat > ~/.config/systemd/user/pi-streamer.service <<'UNIT'
   [Unit]
   Description=BabySentinel Pi audio streamer (ReSpeaker → mediamtx)
   After=mediamtx.service sound.target network-online.target
   Requires=mediamtx.service

   [Service]
   Type=simple
   ExecStartPre=/bin/sleep 4
   ExecStart=/bin/bash %h/BabySentinel/scripts/pi_streamer.sh plughw:1,0
   Restart=always
   RestartSec=3

   [Install]
   WantedBy=default.target
   UNIT

   systemctl --user daemon-reload
   systemctl --user enable --now mediamtx pi-streamer

   # 关键一步：让服务在重启后自动起（无需 SSH 登录）
   loginctl enable-linger $USER
   ```

   `loginctl enable-linger` 在多数发行版可由用户自助 polkit 通过，不需要 sudo。

   日常运维：

   ```bash
   systemctl --user status pi-streamer        # 看状态
   systemctl --user restart pi-streamer       # 改 streamer.sh 后生效
   journalctl --user -u pi-streamer -f        # 看日志
   ```

### 服务端配置

在根 `config.json` 填 `pi_audio_rtsp`：

```json
{
  "pi_host": "192.168.0.20",
  "pi_audio_rtsp": "rtsp://192.168.0.20:8554/respeaker"
}
```

下次 manager 重启 go2rtc 时会自动生成多源 `go2rtc.yaml`：

```yaml
streams:
  baby:
    - rtsp://maomaoyu:***@192.168.0.116:554/stream1#media=video
    - rtsp://192.168.0.20:8554/respeaker#media=audio
```

`#media=video` / `#media=audio` 是 go2rtc 的轨道过滤器，源头丢掉不要的轨道（Tapo 那糟糕的内置音频、mediamtx 的空视频轨）。

### 延迟预算

| 链路 | 延迟 |
|---|---|
| ReSpeaker → ALSA 采集 | 10~30ms |
| ALSA → libopus 编码（20ms 帧 + lowdelay）| ~20ms |
| Pi → 服务端 LAN（UDP RTP）| 5~10ms |
| go2rtc 轨道路由（无转码）| <5ms |
| go2rtc → 浏览器 WebRTC | 50~150ms |
| **Pi 音频端到端** | **~100~200ms** |

Tapo 视频走原路径（200~400ms）。**音频通常会比视频早到 50~150ms**——这个 lipsync 误差对婴儿监控感受不到，对哭声预警反而是好事（音频先于视频抵达你耳朵）。

### 为什么不用 AAC

- AAC 编码器有 ~20ms lookahead（即使 lowdelay 模式也无法消除 LATM 的容器开销）
- AAC 不是 WebRTC 原生 codec，go2rtc 必须转码到 Opus 才能发给浏览器（再 +20~40ms）
- 婴儿监控带宽要求极低（哭/呼吸 32 kbps mono 完全够用），AAC 128k 是 4 倍浪费

切到 Opus 后，从 Pi 一路到浏览器**全程不转码**。

### 录像录到的音频

录像服务 [services/recorder/service.py](services/recorder/service.py) 在写 mp4 时统一转码到 AAC（`-c:a aac -b:a 32k`），Opus 输入兼容，无需改动。回放时显示的就是 Pi 麦的清晰音频。

---

## 录像文件

录像保存在 `recordings/` 目录，按日期分组：

```
recordings/
└── 2026-04-30/
    └── video/
        ├── 10-30-00.mp4   ← 5 分钟一段（segment_s 决定）
        ├── 10-35-00.mp4
        └── index.csv      ← ffmpeg 写的段索引
```

视频编码：H.264（直接复制，无重编码损耗）+ AAC 32kbps，MP4 容器。

传感器时序数据存放在 SQLite `logs/sensors.db`（表 `sensor_readings`，主键 `ts`，按 `date` 索引）。
旧的 `recordings/{date}/sensors.jsonl` 在首次启动时自动导入到 DB，导入完成后文件改名为 `.imported`。

---

## 育儿日志数据库

存储后端为 **SQLite**（`logs/baby_log.db`），schema 是「核心列 + JSON payload」混合：

```sql
entries(
  ts INTEGER PRIMARY KEY,    -- 业务唯一时间戳
  date TEXT NOT NULL,         -- YYYY-MM-DD
  type TEXT NOT NULL,         -- formula/breastfeed/sleep/diaper/...
  time TEXT NOT NULL,         -- HH:MM
  action TEXT,                -- sleep: start/end，其他可空
  payload TEXT,               -- JSON: amount_ml/side/kind/...
  created_at INTEGER
)
```

---

## 目录结构

```
baby-sentinel/
├── manager.py                       # 服务管理器（入口）
├── config.json                      # 跨服务配置（gitignored）
├── config.example.json              # 跨服务配置模板
├── baby_code.json                   # 配对令牌（gitignored）
├── requirements.txt
├── setup.ps1                        # Windows 安装脚本
├── setup.sh                         # macOS / Linux 安装脚本
│
├── shared/                          # 跨服务共享代码
│   ├── config.py                    # ROOT_CFG + load_service_config()
│   ├── alerts.py                    # 告警分发（Discord + Bark + WebSocket）
│   ├── camera.py                    # go2rtc 管理与摄像头健康监控
│   ├── state.py                     # 共享状态 + 可注入 broadcast
│   ├── i18n.py                      # zh / ja 用户可见字符串
│   ├── sensors_db.py                # 传感器时序 SQLite
│   ├── video_util.py                # mp4 完整性校验
│   └── notify/
│       ├── _http.py                 # 共享 Discord HTTP helper
│       ├── discord_bot.py           # Discord Gateway（Slash command）
│       ├── discord_send.py          # Discord REST 告警发送
│       └── bark_send.py             # Bark 多 device key 推送
│
├── services/
│   ├── web/                         # 8080 — Web UI / baby_log REST / Discord Bot
│   │   ├── server.py
│   │   ├── baby_log.py              # 育儿日志（SQLite）
│   │   ├── static/                  # 前端 (index/manager/playback)
│   │   └── config.{json,example.json,py}
│   ├── recorder/                    # 录像服务
│   │   ├── service.py
│   │   └── config.{json,example.json,py}
│   └── voice/                       # 8001 — 语音服务
│       ├── voice_service.py
│       ├── stt.py                   # Whisper STT（faster-whisper / mlx-whisper）
│       ├── llm_agent.py             # tool calling + 对话历史
│       ├── llm/                     # LLM provider 抽象（base/minimax/deepseek）
│       ├── tools/baby_records.py    # LLM 工具：写/撤销育儿日志
│       ├── tts/                     # minimax (WS 流式) / edge-tts
│       └── config.{json,example.json,py}
│
├── agent/                           # 仅剩 pi_streamer.sh：Pi 上 ReSpeaker → mediamtx
│   └── pi_streamer.sh               # 可选；把 Pi 麦克风音频流接到 go2rtc baby 流
│
├── tools/
│   └── test_llm.py                  # LLM toolcall 调试 CLI（跳过 STT/TTS）
│
├── docs/                            # 设计文档（gitignored）
├── bin/                             # go2rtc / ffmpeg 二进制（gitignored）
├── logs/                            # 日志 + baby_log.db / sensors.db（gitignored）
└── recordings/                      # 录像（gitignored）
```

---

## 语音助手（服务端）

`services/voice/voice_service.py` 提供 **STT → LLM tool calling → TTS** 的 HTTP API（端口 8001），由 manager 自动启动。

> **Pi 上的语音客户端（唤醒词 / VAD 录音）已退役**（commit `77265ed`）。当前 voice service 主要被以下两路使用，没有外部音频客户端：
> - **Discord `/log` 命令** —— 自由文本走 LLM 工具调用写育儿日志
> - **`scripts/test_llm.py`** —— 命令行直接 POST 文本，调试 LLM 工具
>
> 如果以后重新接入音频客户端（如 ReSpeaker + openwakeword），再 POST `/voice/process` 即可走完整 STT → LLM → TTS 流程。历史唤醒词模型 `hey_momobot.onnx` 仍在 `wakeword_training/`（gitignored）。

### 架构

```
┌────────────────────────────────────────────┐
│   服务端 voice_service.py  :8001           │
├────────────────────────────────────────────┤
│  POST /voice/process    WAV → STT → LLM →  │
│                         tools → TTS → WAV  │
│  POST /voice/test_llm   text → LLM →       │
│                         tools → text       │
│  GET  /health                              │
│                                            │
│  STT:  faster-whisper (CUDA) /             │
│        mlx-whisper (Apple Silicon)         │
│  LLM:  MiniMax / DeepSeek (thinking)       │
│  TTS:  MiniMax (WS 流式) / edge-tts        │
└────────────────────────────────────────────┘
```

---

### 服务端安装

#### macOS Apple Silicon（M1/M2/M3 推荐）

```bash
bash setup.sh --voice
```

脚本会自动检测 arm64 并安装 `mlx-whisper`（调用 Metal/Neural Engine，large-v3 约 1.5~2s）：

```bash
# 手动安装（可选）:
pip install mlx-whisper
# mlx-whisper 会在首次推理时自动从 HuggingFace 下载模型
```

#### Windows CUDA

```powershell
.\setup.ps1 -Voice
```

先安装 CUDA PyTorch（参考 [pytorch.org](https://pytorch.org/get-started/locally/)），再安装 faster-whisper：

```powershell
# CUDA PyTorch 示例（根据 CUDA 版本调整）:
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install faster-whisper
```

---

### 配置项 `services/voice/config.json`

##### Whisper STT

| 字段 | 默认值 | 说明 |
|---|---|---|
| `whisper_model` | `large-v3` | 模型名：`tiny` / `base` / `small` / `medium` / `large-v3` |
| `whisper_device` | `cuda` | `cuda`（GPU）或 `cpu` |
| `whisper_compute` | `float16` | `float16`（GPU）或 `int8`（CPU 省内存） |
| `whisper_backend` | `auto` | `auto`（macOS arm64 自动用 mlx）/ `faster-whisper` / `mlx` |
| `whisper_beam_size` | `10` | beam 数，越大越准但越慢 |
| `whisper_initial_prompt` | 育儿语料 | 用相关词汇预热模型，提升喂奶/尿布等专有词的识别率 |

##### LLM provider 选择

| 字段 | 默认值 | 说明 |
|---|---|---|
| `llm_provider` | `minimax` | `minimax` 或 `deepseek`，决定走哪家 |

##### LLM — MiniMax

| 字段 | 默认值 | 说明 |
|---|---|---|
| `minimax_api_key` | `""` | MiniMax API Key |
| `minimax_base_url` | `https://api.minimax.io` | API 端点（CN 用 `api.minimaxi.com/v1`，国际 `api.minimax.io`） |
| `minimax_llm_model` | `MiniMax-Text-01` | 模型名，如 `MiniMax-Text-01`、`MiniMax-M2.7` |

##### LLM — DeepSeek

| 字段 | 默认值 | 说明 |
|---|---|---|
| `deepseek_api_key` | `""` | DeepSeek API Key |
| `deepseek_base_url` | `https://api.deepseek.com` | API 端点 |
| `deepseek_model` | `deepseek-v4-flash` | 模型名 |
| `deepseek_thinking_enabled` | `true` | 是否启用 reasoning 模式 |
| `deepseek_reasoning_effort` | `high` | reasoning 强度：`low` / `medium` / `high` |

##### TTS

| 字段 | 默认值 | 说明 |
|---|---|---|
| `tts_provider` | `minimax` | `minimax`（WebSocket 流式）或 `edge`（微软免费 TTS） |
| `tts_model` | `speech-2.6-hd` | MiniMax TTS 模型（仅 `tts_provider=minimax` 时生效） |
| `tts_voice_zh` | `Mandarin_Female` | 中文语音 |
| `tts_voice_ja` | `Japanese_Female` | 日语语音 |
| `tts_voice_en` | `English_Female` | 英语语音 |

##### 鉴权

| 字段 | 默认值 | 说明 |
|---|---|---|
| `internal_api_key` | `""` | 反向调用 web 服务 baby_log API 时的 `X-API-Key`（可选） |

---

### 启动

**服务端：**

```bash
# macOS / Linux
./venv/bin/python services/voice/voice_service.py

# Windows
.\venv\Scripts\python.exe services\voice\voice_service.py
```

访问 `http://localhost:8001/health` 确认服务就绪（首次启动会下载/加载 Whisper 模型，约 10~30s）。manager 默认会拉起 voice service，无需手动启动。

**调试 LLM tool calling（跳过 STT/TTS）：**

```bash
./venv/bin/python scripts/test_llm.py "配方奶 90 毫升"
./venv/bin/python scripts/test_llm.py --lang ja "粉ミルク90ml"
./venv/bin/python scripts/test_llm.py --url http://192.168.1.100:8001 "今日喂了几次"
```

直接对 voice_service 的 `/voice/test_llm` 发文本，看 LLM 怎么调工具、回了什么。**真实落库**，回滚靠"撤销"或在 web UI 删除。

---

### 支持的语音指令

LLM 配置了以下工具，说中文或日语均可触发：

| 意图 | 示例话语 |
|---|---|
| 配方奶 | "刚喂了 90ml 配方奶" / "ミルクを90ml飲んだ" |
| 母乳 | "母乳喂了左边 15 分钟" |
| 换尿布 | "换尿布了，是湿的" |
| 开始睡眠 | "宝宝睡着了" |
| 结束睡眠 | "宝宝醒了" |
| 撤销上条 | "刚才记错了，删掉" / "さっきのを削除して" |
| 追问 | LLM 主动发起追问（如"几毫升？"），用户直接回答 |

---

## 常见问题

**BLE 连接失败 / 找不到设备 / Mac UI 看不到传感器数据**
- BLE 跑在 Pi 上的 [`sense-u-ble`](https://github.com/mao-mao-yu/sense-u-ble) 里。先在 Pi 上确认服务活：`ssh pi 'systemctl --user status sense-u-ble'`
- 确认 Pi 蓝牙开了：`ssh pi 'bluetoothctl show | grep Powered'`，应为 `Powered: yes`。如果 `off-blocked` 见 sense-u-ble README 里的 rfkill unblock 章节
- 确认 Pi 推得到 Mac：sense-u-ble 的 `consumer_url` 必须能连通到 `Mac:8080/api/internal/sensor`（局域网防火墙 / Mac 端 web service 跑着）
- 配对令牌 `~/sense-u-ble/baby_code.json` 缺失或失效：在 Pi 上跑 `./venv/bin/python tools/pairing.py` 重配
- Mac 端 manager UI 里 BLE 卡 status=stopped：通过卡上的 ▶ 启动 重新拉起 Pi 服务（走 SSH）

**摄像头画面无法显示**
- 确认 `tapo_rtsp` 地址正确（VLC 测试 `vlc rtsp://...`）
- 在管理界面查 go2rtc 服务状态
- 浏览器 WebRTC 需要 HTTPS 或 localhost，跨设备访问可能受限

**录像视频每段越来越长 + 前面黑屏**
- 这是 ffmpeg segment muxer 不重置 PTS 的经典 bug
- 已在 [services/recorder/service.py](services/recorder/service.py) 加 `-reset_timestamps 1` 修复
- 旧损坏视频可重新封装：`ffmpeg -i broken.mp4 -c copy -avoid_negative_ts make_zero fixed.mp4`

**Bark 关键告警没有响铃**
- 检查 Bark App 内的「关键警告」开关
- 检查 iOS 系统设置 → 通知 → Bark → 启用关键警告
- 第一次发 critical 推送时 iOS 会弹窗授权，必须点允许

**管理界面手机端 card 超出屏幕**
- 已在新版加响应式（< 768px 单列纵滚动），刷新浏览器即可

**语音服务启动后 Whisper 加载很慢**
- 首次加载 large-v3 约 10~30s，属正常现象（模型约 3GB）
- macOS M3 上 mlx-whisper 首次运行需从 HuggingFace 下载模型缓存，之后秒级加载

**LLM 返回空或 503**
- 检查 `services/voice/config.json` 中对应 provider 的 `*_api_key` 是否正确
- MiniMax `base_url`：国内用 `https://api.minimaxi.com/v1`，国际用 `https://api.minimax.io`
- 配额耗尽时可切 provider：`"llm_provider": "deepseek"`（或反过来）；TTS 切 `"tts_provider": "edge"` 用免费微软 TTS
- 用 `scripts/test_llm.py "配方奶 90 毫升"` 直接打 LLM，比走 STT 链路更快定位是 LLM 还是 Whisper 的问题

---

## 路线图

**已完成：**
- ✅ 语音育儿日记：唤醒词 → Whisper STT → LLM tool calling → TTS 反馈
- ✅ Apple Silicon 支持：mlx-whisper 后端，M3 大约 1.5~2s 完成 large-v3 推理
- ✅ 对话历史（最近 3 轮）+ 撤销上条记录
- ✅ 追问支持：LLM 可发起 follow-up，代理二次录音
- ✅ LLM provider 抽象：MiniMax / DeepSeek 一行配置切换（含 reasoning）
- ✅ 配置分服务管理：每个 service 自己的 `config.json`，根 config 只放跨服务字段
- ✅ Discord Slash command：`/get_sensor_status_now` + `/get_status_today`
- ✅ 白噪音保活：解决 BT/USB 喇叭省电模式导致的 TTS 首字丢失
- ✅ `scripts/test_llm.py` —— 跳过 STT/TTS 直调 LLM 的调试 CLI

**待做：**
- Pi 兼任 BLE 中继：Sense-U 从主机蓝牙移到 Pi，主机蓝牙腾出来
- 唤醒词自定义训练文档
- 入站 API 鉴权：`/voice/process` 和 `/voice/test_llm` 加 `X-API-Key` 校验

---

## 许可

私有项目，无许可声明。
