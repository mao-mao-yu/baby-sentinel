# BabySentinel

婴儿实时监控系统，整合 Sense-U 智能睡眠监测仪（蓝牙传感器）与 Tapo 摄像头，提供 Web 监控界面、育儿日志、Discord 告警和录像回放。

支持 **Windows 10/11** 和 **macOS（Intel / Apple Silicon）**。

---

## 功能

- **实时传感器监控**：呼吸频率、衣内温度、湿度、睡姿、电量、佩戴状态
- **摄像头直播**：通过 go2rtc 将 RTSP 流转为 WebRTC，延迟 < 1 秒
- **告警推送**：俯卧检测、异常呼吸、高/低温，通过 Discord 发送通知
- **喂奶提醒**：可配置喂奶间隔，超时自动提醒
- **育儿日志**：记录喂奶、换尿布、睡眠等事件，统计今日数据
- **录像回放**：3 分钟一段（可通过 `segment_s` 调整）连续录像，支持与传感器数据同步回放
- **服务管理**：独立 Web 界面，可单独启停各微服务
- **哭声检测**（可选）：基于 TensorFlow 的婴儿哭声识别

---

## 系统架构

```
manager.py (9091)       ← 服务管理界面
├── go2rtc              ← RTSP → WebRTC 流媒体转发
├── ble_service.py      ← Sense-U 蓝牙传感器连接
├── server.py (8080)    ← Web UI / API / WebSocket
└── recorder_service.py ← 连续录像 + 传感器时序存档
```

各服务独立运行，互相通过 HTTP 通信，单独重启任一服务不影响其他服务。

---

## 准备工作

### 硬件

- **Sense-U 婴儿监测仪**（贴片式睡眠传感器）
- **Tapo 摄像头**（支持 RTSP 的型号，如 C100/C200/C210/C310）
- 电脑需支持蓝牙（BLE 4.0+）

### 软件

- Python 3.11 或更高版本
- ffmpeg（录像功能需要）
- go2rtc（摄像头直播需要，安装脚本可自动下载）

---

## 安装

### Windows

```powershell
.\setup.ps1
# 同时安装哭声检测依赖（约 2 GB，可选）：
.\setup.ps1 -WithCry
```

### macOS

```bash
bash setup.sh
# 同时安装哭声检测依赖（约 2 GB，可选）：
bash setup.sh --with-cry
```

安装脚本会自动完成：
1. 检查 Python 3.11+
2. 创建虚拟环境 `venv/`
3. 安装 Python 依赖（`requirements.txt`）
4. 下载 go2rtc 二进制文件到 `bin/`
5. 检查 ffmpeg
6. 从 `config.example.json` 复制初始配置文件
7. 创建 `logs/` 和 `recordings/` 目录

---

## 配置

编辑 `config.json`，填写以下必填项：

```jsonc
{
  "ble_address":   "AA:BB:CC:DD:EE:FF",   // Sense-U 蓝牙地址（见下方扫描工具）
  "tapo_rtsp":     "rtsp://user:pass@192.168.1.x:554/stream1",  // Tapo RTSP 地址
  "baby": {
    "birth_date":  "20240101",            // 宝宝生日，YYYYMMDD 格式
    "feed_interval_min": 150              // 喂奶间隔提醒（分钟）
  }
}
```

完整配置项说明：

#### 连接设置

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `ble_address` | — | Sense-U 蓝牙 MAC 地址（必填，见下方扫描工具） |
| `tapo_rtsp` | — | 摄像头 RTSP 地址（必填，格式：`rtsp://用户名:密码@IP:554/stream1`） |
| `ffmpeg_path` | `""` | ffmpeg 可执行文件完整路径，留空则自动从系统 PATH 查找 |

#### 端口设置

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `web_host` | `0.0.0.0` | Web 服务监听地址，`0.0.0.0` 表示允许局域网访问 |
| `web_port` | `8080` | 监控主界面端口 |
| `go2rtc_port` | `1984` | go2rtc 媒体服务端口（WebRTC 直播） |
| `ble_port` | `8082` | BLE 传感器微服务端口 |
| `manager_port` | `9091` | 服务管理界面端口 |

#### 录像设置

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `segment_s` | `180` | 视频分段时长（秒），每隔这么久切一个新的 MP4 文件，默认 3 分钟 |
| `sensor_interval_s` | `5` | 传感器数据写入硬盘的频率（秒），影响回放时的传感器同步精度 |

#### BLE 蓝牙连接

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `ble_scan_timeout_s` | `20` | 每次扫描等待设备出现的最长时间（秒），超时后重试 |
| `ble_connect_timeout_s` | `15` | GATT 连接超时（秒），网络/干扰较多时可适当增大 |
| `ble_poll_interval_s` | `5` | 向设备请求一次完整传感器数据的间隔（秒） |
| `ble_reconnect_delay_s` | `10` | 连接断开后等待多久再重连（秒），过短可能导致 BLE 栈未释放 |

#### 告警行为

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `prone_alert_cooldown_s` | `300` | 同一俯卧状态下两次告警的最短间隔（秒），避免频繁打扰，默认 5 分钟 |
| `feed_repeat_s` | `1800` | 超过喂奶间隔后，每隔多久重复提醒一次（秒），默认 30 分钟 |

#### 通知推送

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `discord_token` | `""` | Discord Bot Token（留空则不推送） |
| `discord_channel_ids` | `[]` | 接收告警的频道 ID 列表（数字 ID） |
| `discord_user_ids` | `[]` | 接收告警私信的用户 ID 列表（数字 ID） |

#### 其他

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `log_level` | `INFO` | 日志详细程度：`DEBUG` 最详细，`INFO` 正常，`WARNING` 仅异常 |
| `baby.birth_date` | `""` | 宝宝生日，格式 `YYYYMMDD`，用于计算日龄和推荐奶量 |
| `baby.weight_g` | `0` | 体重（克），用于计算配方奶推荐量 |
| `baby.feed_type` | `formula` | 喂养方式：`formula`（配方奶）或 `breastfeed`（母乳） |
| `baby.feed_interval_min` | `150` | 喂奶间隔提醒时长（分钟） |

### 获取 Sense-U 蓝牙地址

```bash
# Windows
.\venv\Scripts\python.exe tools\scan_ble.py

# macOS
./venv/bin/python tools/scan_ble.py
```

扫描结果会显示附近 BLE 设备及地址，找到 "Sense" 开头的设备填入 `config.json`。

---

## 首次配对 Sense-U

首次使用前必须运行配对工具，生成认证令牌 `baby_code.json`：

```bash
# Windows
.\venv\Scripts\python.exe tools\pairing.py

# macOS
./venv/bin/python tools/pairing.py
```

按照提示操作（设备靠近电脑，保持唤醒状态）。配对成功后生成 `baby_code.json`，后续连接无需重复配对。

---

## 启动

### 推荐方式：通过管理器启动所有服务

```bash
# Windows
.\venv\Scripts\python.exe manager.py

# macOS
./venv/bin/python manager.py
```

启动后打开管理界面：**http://localhost:9091**

管理器会自动按顺序启动：go2rtc → BLE 传感器 → Web 服务器 → 录像服务。

### 单独启动各服务

```bash
# 仅主 Web 服务（不含 BLE 和录像）
python server.py

# 仅 BLE 传感器服务
python ble_service.py

# 仅录像服务
python recorder_service.py
```

---

## 使用界面

### 监控主界面 — http://localhost:8080

- 实时传感器数据（呼吸、温度、湿度、姿势、电量）
- 摄像头 WebRTC 直播
- 今日育儿日志（喂奶、换尿布、睡眠记录）
- 告警历史

### 录像回放 — http://localhost:8080/playback

- 按日期浏览历史录像
- 3 分钟一段（可通过 `segment_s` 调整）视频片段，点击跳转
- 视频播放时同步显示对应时刻的传感器数据
- 自动切换到下一段

### 服务管理 — http://localhost:9091

- 查看各服务运行状态（running / stopped / crashed）
- 单独启动 / 停止 / 重启任一服务
- 实时查看各服务日志输出
- 服务崩溃时可在此重启，无需重启整个系统

---

## Discord 告警配置

1. 在 [Discord Developer Portal](https://discord.com/developers/applications) 创建 Bot，获取 Token
2. 将 Bot 添加到服务器，获取目标频道 ID
3. 填入 `config.json`：

```json
"discord_token": "your-bot-token",
"discord_channel_ids": [123456789012345678],
"discord_user_ids": []
```

告警类型：
- 🚨 俯卧检测（危险）
- 💨 呼吸异常（危险）
- 🌡️ 温度异常（警告）
- 🍼 喂奶提醒（警告）

---

## 录像文件

录像保存在 `recordings/` 目录，按日期分组：

```
recordings/
└── 2024-01-15/
    ├── video/
    │   ├── 10-30-00.mp4   ← 3 分钟一段（可通过 `segment_s` 调整），H.264 + AAC
    │   ├── 10-31-00.mp4
    │   └── ...
    └── sensors.jsonl      ← 传感器时序数据（每行一条 JSON）
```

视频编码：H.264（直接复制，无重新编码损耗） + AAC 音频 32kbps，MP4 容器。

---

## 哭声检测（可选）

需要额外安装约 2 GB 的 TensorFlow 依赖：

```bash
# Windows
.\setup.ps1 -WithCry

# macOS
bash setup.sh --with-cry
```

在 `server.py` 中取消注释以启用：
```python
asyncio.create_task(camera.cry_loop())
```

检测到哭声时会通过 Discord 发送告警。

---

## 目录结构

```
BabySentinel/
├── manager.py           # 服务管理器（入口）
├── server.py            # Web 服务器
├── ble_service.py       # BLE 传感器服务
├── recorder_service.py  # 录像服务
├── config.json          # 配置文件（不纳入版本管理）
├── config.example.json  # 配置模板
├── baby_code.json        # 配对令牌（不纳入版本管理）
├── requirements.txt
├── requirements-cry.txt # 哭声检测可选依赖
├── setup.ps1            # Windows 安装脚本
├── setup.sh             # macOS/Linux 安装脚本
├── app/
│   ├── ble.py           # BLE 协议解析
│   ├── camera.py        # go2rtc 管理与摄像头健康监控
│   ├── alerts.py        # 告警分发
│   ├── baby_log.py      # 育儿日志
│   ├── config.py        # 配置加载
│   └── state.py         # 共享状态与 WebSocket 广播
├── notify/
│   ├── discord_bot.py   # Discord Gateway 机器人
│   └── discord_send.py  # Discord REST 消息发送
├── static/
│   ├── index.html       # 监控主界面
│   ├── manager.html     # 服务管理界面
│   └── playback.html    # 录像回放界面
├── tools/
│   ├── pairing.py       # Sense-U 首次配对
│   └── scan_ble.py      # BLE 设备扫描
├── cry_detector/
│   └── cry_detector.py  # 哭声检测子进程
├── bin/                 # go2rtc 二进制（不纳入版本管理）
├── logs/                # 日志文件
└── recordings/          # 录像文件（不纳入版本管理）
```

---

## 常见问题

**BLE 连接失败 / 找不到设备**
- 确认 `config.json` 中的 `ble_address` 正确（运行 `tools/scan_ble.py` 确认）
- 确认 `baby_code.json` 存在（运行 `tools/pairing.py` 配对）
- Windows：检查系统蓝牙是否已开启
- macOS：需在系统偏好设置中授权蓝牙权限

**摄像头画面无法显示**
- 确认 `tapo_rtsp` 地址正确（可用 VLC 测试）
- 确认 `bin/go2rtc` 已下载（安装脚本会自动下载）
- 在管理界面检查 go2rtc 服务状态

**录像没有声音 / 视频损坏**
- 确认 ffmpeg 已安装（运行 `ffmpeg -version`）
- macOS 可通过 Homebrew 安装：`brew install ffmpeg`
- Windows 需手动下载并在 `config.json` 的 `ffmpeg_path` 填写完整路径

**管理界面重启服务后仍在运行**
- 确认使用 `manager.py` 启动（直接运行 `server.py` 等不受管理器控制）
- Windows：检查任务管理器是否有残留进程
