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
manager.py (9091)       ← 服务管理界面 / 子进程编排（含心跳监测、孤儿清理、自动重启）
├── go2rtc              ← RTSP → WebRTC 流媒体转发
├── ble_service.py (8082)
│                       ← Sense-U 蓝牙传感器连接（独立进程，崩溃不影响主服务）
├── server.py (8080)    ← Web UI / baby_log REST / WebSocket 广播
└── recorder_service.py ← 连续录像（ffmpeg）+ 传感器时序存档
```

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
6. 从 `config.example.json` 复制初始 `config.json`
7. 创建 `logs/` 和 `recordings/` 目录

---

## 配置

编辑 `config.json`，**必填项**：

```jsonc
{
  "ble_address":   "AA:BB:CC:DD:EE:FF",   // Sense-U 蓝牙地址
  "tapo_rtsp":     "rtsp://user:pass@192.168.1.x:554/stream1",
  "baby": {
    "birth_date":  "20240101",
    "feed_interval_min": 150
  }
}
```

### 完整配置项

#### 连接

| 字段 | 默认值 | 说明 |
|---|---|---|
| `ble_address` | — | Sense-U 蓝牙地址。**Windows/Linux** 写真实 MAC（如 `D4:92:DB:03:D7:59`）。**macOS** 写 CoreBluetooth UUID（每台 Mac 不同，扫描得到，如 `0B5602EE-…`） |
| `ble_mac` | `""` | 仅 macOS 需要：设备真实 MAC 地址，用于构造 GATT 特征 UUID。Windows/Linux 留空（自动从 `ble_address` 取） |
| `ble_dump_raw` | `false` | 诊断开关：开启后所有 BLE 数据帧 hex dump 进日志，调试协议时用 |
| `tapo_rtsp` | — | 摄像头 RTSP 地址（含密码） |
| `ffmpeg_path` | `""` | ffmpeg 路径，留空自动从 `bin/` 或系统 PATH 查找 |
| `go2rtc_path` | `""` | go2rtc 路径，同上 |

> macOS 上 bleak 用的是 CoreBluetooth UUID（每台机器自己分配，不能用 MAC）。`ble_mac` 字段是给 GATT 特征 UUID 拼接用的，跟设备 MAC 一致，跨设备通用。Windows/Linux 这两个字段功能合一，只填 `ble_address`。

#### 端口

| 字段 | 默认 | 说明 |
|---|---|---|
| `web_host` | `0.0.0.0` | Web 服务监听地址，`0.0.0.0` 允许局域网访问 |
| `web_port` | `8080` | 监控主界面端口 |
| `go2rtc_port` | `1984` | go2rtc WebRTC 端口 |
| `ble_port` | `8082` | BLE 传感器微服务端口 |
| `manager_port` | `9091` | 管理界面端口 |

#### 录像

| 字段 | 默认 | 说明 |
|---|---|---|
| `segment_s` | `300` | 视频分段时长（秒），默认 5 分钟一段 |

> 传感器数据写入与 `ble_poll_interval_s` 同频率，每次成功 BLE 轮询都落入 SQLite (`logs/sensors.db`)。

#### BLE 时序

| 字段 | 默认 | 说明 |
|---|---|---|
| `ble_scan_timeout_s` | `20` | 扫描设备最长等待（秒） |
| `ble_connect_timeout_s` | `15` | GATT 连接超时（秒） |
| `ble_poll_interval_s` | `2` | 0xBA 数据 polling 间隔（秒） |
| `ble_reconnect_delay_s` | `10` | 断开后重连前等待（秒） |
| `ble_health_timeout_s` | `10` | server 监测 ble_service 心跳超时（秒），超时即标 `ble_ok=false` |

#### 告警

| 字段 | 默认 | 说明 |
|---|---|---|
| `prone_alert_threshold_s` | `30` | 俯卧持续多少秒**才第一次**报警 |
| `prone_alert_cooldown_s` | `300` | 仍在俯卧时**重复**报警的最小间隔（秒） |
| `breath_alert_threshold_rate` | `8` | 呼吸频率低于此值（次/分）触发告警 |
| `breath_alert_duration_s` | `20` | 必须连续低呼吸多少秒（且必须贴身）才报警 |
| `breath_alert_cooldown_s` | `300` | 重复呼吸告警的最小间隔（秒） |
| `feed_repeat_s` | `1800` | 喂奶到点后每隔多久重复提醒（秒） |

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

### 获取 Sense-U 蓝牙地址

```bash
# Windows
.\venv\Scripts\python.exe tools\scan.py

# macOS
./venv/bin/python tools/scan.py
```

扫描结果会列出附近 BLE 设备 + 地址 + 名字，找到 `Sense-U Baby Pro` 那一项填进 `config.json`。

---

## 首次配对 Sense-U

首次使用前必须配对一次，生成认证令牌 `baby_code.json`：

```bash
# Windows
.\venv\Scripts\python.exe tools\pairing.py

# macOS
./venv/bin/python tools/pairing.py
```

按提示长按设备进入配对模式（蓝灯快闪）。配对成功后会写入 `baby_code.json`，**baby_code 跨平台通用**——你可以把这个文件复制到另一台机器（如 Pi）继续用。

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

manager 会按顺序启动：go2rtc → ble_service → server → recorder。

### 单独启动各服务（调试用）

```bash
python ble_service.py     # 仅 BLE 传感器
python server.py          # 仅主 Web 服务
python recorder_service.py # 仅录像
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

Discord Bot 还提供 Slash command `/get_babystatus`，**主动查询当前状态**（在 Discord 客户端里输 `/get_babystatus` 即可）。

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

### 从旧版 JSON 迁移

旧版本（< 2026-04）使用 `logs/baby_log.json`。升级后第一次启动需要手动迁一次：

```bash
# 如果存在 logs/baby_log.json，运行：
./venv/bin/python tools/migrate_baby_log.py
```

迁移工具会：
- 检测 `logs/baby_log.json` + DB 为空才执行（避免覆盖）
- 重复 ts 自动 +1 去重，零数据丢失
- 完成后 JSON 改名为 `.bak` 作为回滚备份

---

## 目录结构

```
baby-sentinel/
├── manager.py              # 服务管理器（入口）
├── server.py               # Web 服务器
├── ble_service.py          # BLE 传感器服务
├── recorder_service.py     # 录像服务
├── config.json             # 用户配置（gitignored）
├── config.example.json     # 配置模板（默认值数据源）
├── baby_code.json          # 配对令牌（gitignored）
├── requirements.txt
├── setup.ps1               # Windows 安装脚本
├── setup.sh                # macOS / Linux 安装脚本
├── app/
│   ├── ble.py              # BLE 协议解析（Sense-U Baby Pro）
│   ├── camera.py           # go2rtc 管理与摄像头健康监控
│   ├── alerts.py           # 告警分发（Discord + Bark + WebSocket）
│   ├── baby_log.py         # 育儿日志（SQLite）
│   ├── config.py           # 配置加载
│   └── state.py            # 共享状态 + 可注入 broadcast
├── notify/
│   ├── _http.py            # 共享 Discord HTTP helper
│   ├── discord_bot.py      # Discord Gateway 客户端（Slash command）
│   ├── discord_send.py     # Discord REST 告警发送
│   └── bark_send.py        # Bark 多 device key 推送
├── static/
│   ├── index.html          # 监控主界面
│   ├── manager.html        # 服务管理界面
│   ├── playback.html       # 录像回放界面
│   ├── config.js           # 前端常量 + i18n
│   └── images/             # 姿势图标
├── tools/
│   ├── scan.py             # BLE 设备扫描
│   ├── pairing.py          # Sense-U 首次配对
│   ├── migrate_baby_log.py # JSON → SQLite 迁移工具
│   ├── discover.py         # GATT 服务发现（调试用）
│   ├── adv_scan.py         # BLE 广播扫描（调试用）
│   └── import_log.py       # 第三方日志导入（如 Piyo）
├── docs/                   # 设计文档（gitignored，新内容不自动追踪）
├── bin/                    # go2rtc / ffmpeg 二进制（gitignored）
├── logs/                   # 日志 + baby_log.db（gitignored）
└── recordings/             # 录像（gitignored）
```

---

## 常见问题

**BLE 连接失败 / 找不到设备**
- 确认 `config.json` 中的 `ble_address` 正确（运行 `tools/scan.py` 重新扫描）
- 确认 `baby_code.json` 存在（首次必须 `tools/pairing.py` 配对）
- macOS 需在系统设置 → 隐私与安全性 → 蓝牙中授权终端 / VS Code
- macOS 上 `ble_address` 必须是 CoreBluetooth UUID 不是 MAC，且 `ble_mac` 必须填真实 MAC

**摄像头画面无法显示**
- 确认 `tapo_rtsp` 地址正确（VLC 测试 `vlc rtsp://...`）
- 在管理界面查 go2rtc 服务状态
- 浏览器 WebRTC 需要 HTTPS 或 localhost，跨设备访问可能受限

**录像视频每段越来越长 + 前面黑屏**
- 这是 ffmpeg segment muxer 不重置 PTS 的经典 bug
- 已在新版 [recorder_service.py](recorder_service.py) 加 `-reset_timestamps 1` 修复
- 旧损坏视频可重新封装：`ffmpeg -i broken.mp4 -c copy -avoid_negative_ts make_zero fixed.mp4`

**Bark 关键告警没有响铃**
- 检查 Bark App 内的「关键警告」开关
- 检查 iOS 系统设置 → 通知 → Bark → 启用关键警告
- 第一次发 critical 推送时 iOS 会弹窗授权，必须点允许

**管理界面手机端 card 超出屏幕**
- 已在新版加响应式（< 768px 单列纵滚动），刷新浏览器即可

---

## 路线图

下一步开发计划见 [docs/voice-baby-log.md](docs/voice-baby-log.md)：

- **语音育儿日记**：树莓派 Zero 2W + ReSpeaker USB Mic Array → 唤醒词检测（openWakeWord）→ 本地 STT（faster-whisper）→ Claude API tool_use 调 baby_log API
- **Pi 兼任 BLE 中继**：Sense-U 从 Mac mini 蓝牙总线移到 Pi，Mac 蓝牙腾出来给键鼠 / AirPods
- **目标**：唤醒 → 说一句 → 自动写日志 → TTS 反馈，端到端延迟 < 2.5s

实施分 5 个 Phase，每个 Phase 独立可验证。详见 docs。

---

## 许可

私有项目，无许可声明。
