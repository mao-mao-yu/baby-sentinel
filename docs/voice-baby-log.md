# 语音育儿日记 — 设计 + 实施手册

> 把宝宝旁边的麦克风变成"听一句话就记一条 log"的入口。
> 「喂了 80 毫升配方奶」「拉便便了」之类的指令一句话搞定，无需开 App。

---

## 0. 一句话目标

唤醒词 → 说一句 → 自动写 baby_log → TTS 反馈"已记录"，**端到端 ≤ 2.5 秒**。
**录音不出门**（只把转录后的短文本发给 Claude），不焊接、不接 GPIO，**Pi 顺手做 BLE 中继**把 Sense-U 传感器从 Mac mini 蓝牙总线上腾出来。

---

## 1. 整体架构

```
┌──────────────── 婴儿床旁（一根 micro USB 电源 + Wi-Fi）────────────────┐
│                                                                       │
│   ReSpeaker Mic Array v2.0                                            │
│         │ USB-A (公)                                                  │
│         ↓                                                             │
│   有源 USB Hub (可选，¥30，强烈建议)                                    │
│         │ USB-A (公)                                                  │
│         ↓ 经 OTG 转接头                                                │
│                                                                       │
│   ┌──────────── 树莓派 Zero 2W (Linux) ─────────────────┐             │
│   │                                                     │             │
│   │  ① ble_service.py（迁自 Mac mini）                  │             │
│   │     ├─ Bluetooth → Sense-U Pro (GATT 0xBA polling) │             │
│   │     └─ HTTP POST → Mac:8080/api/internal/sensor    │             │
│   │                                                     │             │
│   │  ② ffmpeg                                           │             │
│   │     └─ ALSA(arecord) → Opus 编码 → RTP/UDP →       │             │
│   │        Mac:5004                                     │             │
│   │                                                     │             │
│   │  ③ systemd 管理两个服务自启                          │             │
│   │                                                     │             │
│   └─────────────────────────────────────────────────────┘             │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
                                 │
                                 │  Wi-Fi（家庭路由器）
                                 ▼
┌──────────────────────── Mac mini (M2) ──────────────────────────┐
│                                                                 │
│   manager.py (统一进程管理)                                       │
│   ├─ server.py    (FastAPI: WebSocket / baby_log REST)          │
│   ├─ recorder_service.py                                        │
│   └─ voice_agent.py (新增)                                       │
│        ├─ ① ffmpeg 拉 RTP 5004 → 16kHz mono PCM                  │
│        ├─ ② openWakeWord 监听唤醒词 (CPU < 1%)                    │
│        ├─ ③ VAD 圈定话音段 (~3-5s)                                │
│        ├─ ④ faster-whisper STT (small.zh, ~800ms)                │
│        ├─ ⑤ Claude Haiku 4.5 + tool_use (~600ms)                 │
│        ├─ ⑥ POST 127.0.0.1:8080/api/log (X-API-Key 鉴权)         │
│        └─ ⑦ macOS `say` "已记录" (异步)                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

只有 ⑤ 出网（发**文本**给 Claude）。其余全部本地。

---

## 2. 硬件清单（已购）

| 项 | 型号 | 备注 |
|---|---|---|
| 单板机 | Raspberry Pi Zero 2 W | ✓ 已买 |
| 麦克风 | ReSpeaker Mic Array v2.0（XVF3000） | ✓ 已买 |
| 电源 | 5V/2.4A+ USB-A 充电头 + micro USB 数据线 | ✓ 已买 |
| OTG 转接头 | micro USB 公 → USB-A 母 | ✓ 已买 |
| microSD | 32GB 以上 Class 10 / A1 | ✓ 已买 |
| **建议加购** | **有源 USB Hub** (¥30) | OTG 直供 ReSpeaker 偶有失稳，加 hub 一劳永逸 |
| **建议加购** | **铝合金外壳** (¥80) | 24/7 跑稳定性 |

---

## 3. Phase 0 — 树莓派初始化

### 3.1 烧录 Raspberry Pi OS

电脑（Mac/Win）装 [Raspberry Pi Imager](https://www.raspberrypi.com/software/)：

1. 选 OS：**Raspberry Pi OS Lite (64-bit)**（无桌面，省内存）
2. 选 SD 卡
3. **点齿轮图标，预配置**（关键步骤，不做的话开机后无法 SSH）：
   - ✅ 主机名：`babypi.local`
   - ✅ 启用 SSH，密码登录
   - ✅ 用户名：`pi`，密码：自己设
   - ✅ Wi-Fi SSID + 密码（家里的 2.4GHz 或 5GHz 都行，Pi Zero 2W 都支持）
   - ✅ Wi-Fi 国家：JP（如果在日本）
   - ✅ 时区：`Asia/Tokyo`
4. **WRITE** 按下去，5 分钟左右

### 3.2 物理组装

```
[墙插]
   │
   └─ [USB-A 充电头 5V/2.4A]
         │
         └─ [micro USB 数据线]
                  │
                  └─ Pi Zero 2W 左侧 micro USB（PWR IN）

   Pi Zero 2W 右侧 micro USB（DATA）
       │
       └─ [OTG 转接头]
              │
              └─ [有源 USB Hub] ← 自带 5V 电源
                     │
                     └─ [ReSpeaker v2.0]
```

SD 卡插 Pi、上电、绿色 LED 亮起呼吸闪烁就是启动 OK。

### 3.3 第一次 SSH 进入

Mac 终端：
```bash
ssh pi@babypi.local
# 第一次会问 fingerprint，输 yes，再输你设的密码
```

进去后做基础更新和安装：
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv git ffmpeg alsa-utils \
                    bluetooth bluez libbluetooth-dev pulseaudio \
                    avahi-daemon
```

### 3.4 验证 ReSpeaker 识别

```bash
arecord -l
```

期望看到：
```
**** List of CAPTURE Hardware Devices ****
card 1: ArrayUAC10 [ReSpeaker 4 Mic Array (UAC1.0)], device 0: USB Audio [USB Audio]
  Subdevices: 1/1
  Subdevice #0: subdevice #0
```

记下 **`card 1`** 的编号（你的可能是 1 或 2，不一定）。后面 ffmpeg 命令要用。

录 5 秒测试：
```bash
arecord -D plughw:1,0 -f S16_LE -r 16000 -c 1 -d 5 /tmp/test.wav
aplay /tmp/test.wav    # 没扬声器就 scp 回 Mac 听
```

---

## 4. Phase 1 — BLE 中继迁移到 Pi

### 4.1 项目代码同步

```bash
cd ~
git clone https://github.com/mao-mao-yu/baby-sentinel.git
cd baby-sentinel
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install fastapi uvicorn bleak websockets
```

### 4.2 调整 config.json

Pi 上 bleak 用的是 Linux BlueZ 后端，**直接用真实 MAC 地址**——不像 macOS 要 CoreBluetooth UUID。我们之前为 macOS 加的 `ble_mac` 兼容字段刚好派上用场：

`config.json`（Pi 上的）：
```json
{
  "ble_address": "D4:92:DB:03:D7:59",
  "ble_mac": "",
  "web_port": 8080,
  "ble_port": 8082,
  "..."
}
```

注意 **Pi 上 `ble_address` 是 MAC，`ble_mac` 留空自动回退**。这跟当前 macOS 配置（`ble_address` = CoreBluetooth UUID + `ble_mac` = MAC）不一样——两台机器各有自己的 `config.json`，git 不要同步这个文件。

`ble_service.py` 还要把数据 POST 到 Mac 上的 server.py，所以加个 `web_host_remote` 配置（或直接改代码硬编码 Mac 的 IP）：

```python
# ble_service.py 里把这行改一下
WEB_PORT = CFG.get("web_port", 8080)
WEB_HOST = CFG.get("web_host_remote", "127.0.0.1")  # 默认本机；Pi 上设成 Mac 的 IP
# ...
f"http://{WEB_HOST}:{WEB_PORT}/api/internal/sensor"
```

config.json 加：
```json
"web_host_remote": "192.168.1.100"   ← Mac mini 的局域网 IP
```

Mac 的 IP 可以在 macOS 的「系统设置 → 网络」看，或者：
```bash
# Mac 终端
ipconfig getifaddr en0   # Wi-Fi
ipconfig getifaddr en1   # 有线
```

建议给 Mac 在路由器后台分配**静态 IP**（DHCP 保留），避免每次重启 IP 变了 Pi 找不着。

### 4.3 baby_code.json 同步

Sense-U 之前在 Mac 上配过对，`baby_code.json` 存着会话密钥。**复制这个文件到 Pi**：

```bash
# 在 Mac 上
scp /Users/maomaoyu/Desktop/baby-sentinel/baby_code.json pi@babypi.local:~/baby-sentinel/
```

baby_code 跨 host 通用（之前讨论过），不需要重新配对。

### 4.4 跑起来验证

Pi 上：
```bash
cd ~/baby-sentinel
source venv/bin/activate
python ble_service.py
```

期望看到：
```
[BLE Service] 启动 http://localhost:8082
[BLE] 找到设备，连接中...
[BLE] 已连接，等待 GATT 就绪...
[BLE] GATT 服务发现完成 (3 个)
[BLE] 订阅 CHAR_1 / CHAR_4 / 已订阅...
[BLE] 鉴权成功！
[BLE] 连接已活跃
```

Mac 端浏览器打开 `http://localhost:8080/`，传感器数据应该开始更新。

### 4.5 systemd 自启

Pi 上创建 `/etc/systemd/system/baby-ble.service`：

```ini
[Unit]
Description=BabySentinel BLE Service (Sense-U → Mac mini)
After=network-online.target bluetooth.service
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/baby-sentinel
ExecStart=/home/pi/baby-sentinel/venv/bin/python -u ble_service.py
Restart=on-failure
RestartSec=10
StandardOutput=append:/home/pi/baby-sentinel/logs/ble.log
StandardError=inherit

[Install]
WantedBy=multi-user.target
```

启用：
```bash
sudo systemctl daemon-reload
sudo systemctl enable baby-ble
sudo systemctl start baby-ble
sudo systemctl status baby-ble    # 看是否 active (running)
```

**到此 Phase 1 结束**——Pi 已经替代 Mac mini 做 BLE 中继，重启 Mac 现有的 manager.py 时把 ble 服务从 SERVICES 删掉（或者注释 `_lifespan` 里 ble 启动）：

```python
# manager.py SERVICES 字典里
# 删除或注释掉 "ble": {...}
```

---

## 5. Phase 2 — 音频推流

### 5.1 ffmpeg 推 RTP

Pi 上：
```bash
ffmpeg -loglevel warning \
  -f alsa -ac 1 -ar 16000 -i plughw:1,0 \
  -c:a libopus -b:a 32k -frame_duration 20 \
  -f rtp rtp://192.168.1.100:5004
```

参数说明：
- `-f alsa -i plughw:1,0` — 从 ReSpeaker（card 1）拿音频
- `-ar 16000 -ac 1` — 16kHz 单声道（Whisper 训练分布）
- `-c:a libopus -b:a 32k` — opus 32 kbps，**带宽小到忽略不计**
- `-f rtp rtp://Mac的IP:5004` — RTP over UDP

### 5.2 Mac mini 端拉流验证

Mac 上 ffmpeg 拉流写到文件试听：
```bash
ffmpeg -i rtp://0.0.0.0:5004 -t 10 /tmp/test_from_pi.wav
afplay /tmp/test_from_pi.wav
```

听到自己的声音 = 链路打通。

### 5.3 systemd 自启

Pi 上 `/etc/systemd/system/baby-audio.service`：

```ini
[Unit]
Description=BabySentinel Audio RTP Stream → Mac mini
After=network-online.target sound.target
Wants=network-online.target

[Service]
Type=simple
User=pi
ExecStart=/usr/bin/ffmpeg \
  -loglevel warning \
  -f alsa -ac 1 -ar 16000 -i plughw:1,0 \
  -c:a libopus -b:a 32k -frame_duration 20 \
  -f rtp rtp://192.168.1.100:5004
Restart=on-failure
RestartSec=10
StandardOutput=append:/home/pi/baby-sentinel/logs/audio.log
StandardError=inherit

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable baby-audio
sudo systemctl start baby-audio
```

---

## 6. Phase 3 — Mac 端 voice_agent

### 6.1 安装依赖

```bash
# Mac 终端
cd /Users/maomaoyu/Desktop/baby-sentinel
./venv/bin/pip install openwakeword faster-whisper anthropic webrtcvad
```

### 6.2 voice_agent.py 骨架

新文件 `voice_agent.py`（项目根目录）：

```python
"""BabySentinel 语音代理 — 拉 RTP → 唤醒词 → STT → Claude tool_use → 写 baby_log"""

import asyncio, json, os, subprocess, urllib.request
from anthropic import Anthropic
from openwakeword.model import Model as WakeModel
from faster_whisper import WhisperModel

from app.config import CFG, log

WEB_PORT  = CFG.get("web_port", 8080)
API_KEY   = CFG.get("internal_api_key", "")
RTP_PORT  = CFG.get("audio_rtp_port", 5004)

WAKE_THRESHOLD = 0.5
SAMPLE_RATE    = 16000
CHANNELS       = 1

WHISPER  = WhisperModel("small", device="cpu", compute_type="int8")
WAKE     = WakeModel(wakeword_models=["alexa"], inference_framework="onnx")  # 占位，后续训自定义
CLAUDE   = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

TOOL = {
    "name": "log_baby_event",
    "description": "记录宝宝事件到育儿日志",
    "input_schema": {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["formula","breastfeed","bottle_milk",
                                                "sleep","wake","wet","poop",
                                                "temperature","height","weight","bath","pump","note"]},
            "amount_ml": {"type": "number"},
            "duration_min": {"type": "number"},
            "side": {"type": "string", "enum": ["left","right","both"]},
            "left_min": {"type": "number"},
            "right_min": {"type": "number"},
            "value": {"type": "number"},
            "kind": {"type": "string", "enum": ["wet","dirty","both"]},
            "amount": {"type": "string", "enum": ["少","正常","多"]},
            "consistency": {"type": "string"},
            "color": {"type": "string"},
            "text": {"type": "string"},
        },
        "required": ["type"],
    },
}


def _post_log(entry: dict):
    """调本地 baby_log API。type→action 这种字段后端自己处理。"""
    data = json.dumps(entry).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{WEB_PORT}/api/log",
        data=data, method="POST",
        headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
    )
    urllib.request.urlopen(req, timeout=3).read()


def _say(msg: str):
    """macOS 原生 TTS"""
    subprocess.Popen(["say", "-v", "Kyoko", msg])  # 日语女声


async def transcribe(pcm: bytes) -> str:
    segs, _ = WHISPER.transcribe(pcm, language="zh", vad_filter=True)
    return "".join(s.text for s in segs).strip()


async def ask_claude(text: str) -> dict | None:
    resp = CLAUDE.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        tools=[TOOL],
        messages=[{"role":"user", "content": f"用户说：{text}"}],
    )
    for block in resp.content:
        if block.type == "tool_use" and block.name == "log_baby_event":
            return block.input
    return None


async def main():
    # ffmpeg 把 RTP 解码成 16kHz mono PCM stdout
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-loglevel", "error",
        "-i", f"rtp://0.0.0.0:{RTP_PORT}",
        "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS),
        "-f", "s16le", "pipe:1",
        stdout=asyncio.subprocess.PIPE,
    )

    log.info("[Voice] 监听唤醒词中...")
    chunk = b""
    while True:
        chunk += await proc.stdout.read(2048)
        if len(chunk) < 2 * SAMPLE_RATE * 0.08:  # 80ms 块
            continue
        # openWakeWord 期望 1280 samples (80ms @ 16kHz) int16
        scores = WAKE.predict(np.frombuffer(chunk[:2560], dtype=np.int16))
        chunk = chunk[2560:]
        if max(scores.values()) < WAKE_THRESHOLD:
            continue

        log.info("[Voice] 检测到唤醒词，开始录音")
        # ... 此处用 webrtcvad 圈定 1.5s 静音停止
        # ... 录到 pcm
        text = await transcribe(pcm)
        log.info(f"[Voice] 转录: {text}")

        entry = await ask_claude(text)
        if entry:
            _post_log(entry)
            _say("已记录")
            log.info(f"[Voice] 已写入 baby_log: {entry}")
        else:
            _say("没听清")


if __name__ == "__main__":
    asyncio.run(main())
```

> 上面的代码是骨架，具体的 VAD 录音逻辑（用 `webrtcvad` 检测 1.5s 静音作为话音结束）和错误处理需要在 Phase 3 实施时补完。这里给出整体形状，让你看清楚各块怎么衔接。

### 6.3 加进 manager.py SERVICES

```python
# manager.py 的 SERVICES 字典
"voice": {
    "name": "Voice Agent",
    "icon": "🎙️",
    "desc": "唤醒词 + STT + Claude tool_use",
    "cmd":  [sys.executable, "-u", "voice_agent.py"],
    "port": None,
},
```

`_lifespan` 启动列表加上 `"voice"`。

### 6.4 测试流程

1. 离 Pi 1m 说："Alexa（占位唤醒词），喂了 80 毫升配方奶"
2. 期望日志：
   ```
   [Voice] 检测到唤醒词，开始录音
   [Voice] 转录: 喂了80毫升配方奶
   [Voice] 已写入 baby_log: {'type': 'formula', 'amount_ml': 80}
   ```
3. macOS 喇叭说"已记录"
4. 浏览器 baby_log 列表立刻出现新条目

---

## 7. Phase 4 — API 鉴权

### 7.1 config.json 加 token

```json
"internal_api_key": "随机32字节hex",
```

生成：
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 7.2 server.py 中间件

`server.py` 加（在 `app = FastAPI(...)` 之后）：

```python
from fastapi import HTTPException, Request

_PROTECTED_PREFIXES = ("/api/log", "/api/internal/")

@app.middleware("http")
async def _api_key_check(request: Request, call_next):
    path = request.url.path
    if any(path.startswith(p) for p in _PROTECTED_PREFIXES):
        # 仅当客户端不在 127.0.0.1（本机）时才校验
        client = request.client.host if request.client else ""
        if client not in ("127.0.0.1", "::1") and \
           request.headers.get("X-API-Key") != CFG.get("internal_api_key", ""):
            raise HTTPException(status_code=401, detail="invalid api key")
    return await call_next(request)
```

> 注意：voice_agent 跑在 Mac 本机，请求来自 `127.0.0.1` 直接放行；Pi 上 ble_service 走局域网过来必须带 X-API-Key 才能 POST `/api/internal/sensor`。

### 7.3 Pi 端 ble_service.py 带 token

`ble_service.py` 的 HTTP push 改一下：
```python
req = urllib.request.Request(
    f"http://{WEB_HOST}:{WEB_PORT}/api/internal/sensor",
    data=payload,
    headers={
        "Content-Type": "application/json",
        "X-API-Key":    CFG.get("internal_api_key", ""),
    },
    method="POST",
)
```

Pi 的 `config.json` 写同一个 token。

---

## 8. 故障排查

| 症状 | 检查 | 修复 |
|---|---|---|
| Pi 启动后 SSH 不通 | 路由器 DHCP 表看 babypi 是否拿到 IP | Wi-Fi 密码错？2.4G/5G 频段对？SD 重新刷 |
| `arecord -l` 看不到 ReSpeaker | `lsusb` 看 USB 是否枚举 | 1. OTG 头反了 2. 供电不足，加有源 hub 3. 换 USB 数据线 |
| Pi 启动右上角红色闪电 | `vcgencmd get_throttled` | `0x10005` = 欠压；换粗 micro USB 数据线或更高功率充电头 |
| BLE 找不到设备 | `bluetoothctl scan on` 是否能看到 D4:92:... | 1. Sense-U 离 Pi > 5m 2. baby_code.json 没复制 3. Sense-U 还连着 Mac 没断 |
| BLE 鉴权失败 | 日志 `[BLE] 鉴权失败！` | baby_code 跨平台不通用？删除 Pi 上的 baby_code.json，重新跑 `tools/pairing.py` |
| Mac 拉不到 RTP | 防火墙 5004/UDP 被挡 | macOS 系统设置 → 网络 → 防火墙 → 允许 ffmpeg |
| 唤醒词误触发 | 看日志触发频率 | 调高 `WAKE_THRESHOLD`（默认 0.5 → 0.7）；训练自定义唤醒词 |
| 唤醒词不响应 | 麦克风音量太小 | ReSpeaker 板载 DSP 自动增益；试着说话凑近 1m |
| Claude 调用慢 | 看 anthropic API 响应时间 | 日本到 us-east 走海缆约 150ms，正常；可换 claude-haiku-4-5 |

### 关键诊断命令（Pi 上）

```bash
# 服务状态
sudo systemctl status baby-ble baby-audio

# 实时日志
journalctl -u baby-ble -f
journalctl -u baby-audio -f

# 项目自己的日志
tail -f ~/baby-sentinel/logs/ble.log
tail -f ~/baby-sentinel/logs/audio.log

# 蓝牙状态
sudo bluetoothctl info D4:92:DB:03:D7:59
sudo systemctl status bluetooth

# USB 状态
lsusb              # 看 ReSpeaker 是否在
arecord -l         # 看 ALSA 是否识别

# 供电状态（任何 0x1xxxx 都说明欠压过）
vcgencmd get_throttled

# 温度（持续 > 70°C 要散热）
vcgencmd measure_temp
```

---

## 9. 成本 / 延迟 / 维护

### 成本

| 项 | 一次性 | 月度 |
|---|---|---|
| Pi Zero 2W + 外壳 + SD + 电源 + OTG | ~¥350（已购） | - |
| ReSpeaker Mic Array v2.0 | ~¥600（已购） | - |
| 有源 USB Hub（建议） | ¥30 | - |
| Mac mini | 已有 | - |
| Claude Haiku API | - | ~$0.4 / 月（按每天 10 次记录） |
| **运行成本** | - | **约 ¥3 / 月** |

### 端到端延迟

| 阶段 | 耗时 |
|---|---|
| 唤醒词检测（说完唤醒词到检测到） | ~200ms |
| 用户说话（平均） | ~3000ms |
| VAD 静音判定 | ~300ms |
| RTP 网络抖动 | ~50ms |
| Whisper STT | ~800ms |
| Claude API tool_use | ~600ms |
| 本地 POST /api/log | ~50ms |
| TTS "已记录"（异步） | ~300ms（不计入感知） |
| **从话音落下到反馈** | **~1.8-2.0s** |

### 维护

| 项 | 周期 |
|---|---|
| Pi 系统更新 | 月度 `sudo apt update && sudo apt upgrade` |
| Pi 重启（清内存） | 季度 `sudo reboot` |
| ReSpeaker 固件升级 | 一次性，详见 Seeed wiki |
| Claude API key 轮换 | 半年 |
| baby_log.db 备份 | 每周 `cp logs/baby_log.db logs/baby_log.db.$(date +%Y%m%d)` |

---

## 10. 不做的事 / 不考虑

- **不做云端 STT**：录音不出门是底线
- **不做本地 LLM**：tool_use 准确率 + 中日双语理解，本地小模型差太远
- **不做焊接 / GPIO 接线**：USB + 蓝牙 + Wi-Fi 全靠插
- **不在 Mac mini 上保留 BLE 直连**：迁到 Pi 上更稳
- **不在 Pi 上跑唤醒词**：Pi Zero 2W 性能边界，模型/数据出问题难调试；Mac mini 闲置算力多得是
- **不做多麦克风波束（多 Pi 协同）**：Phase 3 的扩展，先单点跑稳

---

## 11. 实施顺序（Checklist）

**Phase 0 — 树莓派开机能用** (~30 分钟)
- [ ] Imager 烧录 Pi OS Lite 64 + 预配置 SSH/Wi-Fi
- [ ] 物理装配 + 上电
- [ ] `ssh pi@babypi.local` 进入
- [ ] `sudo apt update && upgrade` + 装基础包
- [ ] `arecord -l` 识别 ReSpeaker
- [ ] 录音回放测试

**Phase 1 — BLE 中继迁移** (~30 分钟)
- [ ] git clone 项目
- [ ] venv + pip install
- [ ] 复制 baby_code.json
- [ ] 改 config.json：`ble_address` = MAC，`web_host_remote` = Mac IP
- [ ] 手动跑 `python ble_service.py` 验证
- [ ] systemd 自启 baby-ble
- [ ] manager.py 删 ble 服务定义

**Phase 2 — 音频推流** (~20 分钟)
- [ ] ffmpeg 命令验证 RTP 推流
- [ ] Mac 端 ffmpeg 拉流听到声音
- [ ] systemd 自启 baby-audio

**Phase 3 — 语音代理** (~2-4 小时，含调试)
- [ ] Mac 装 openwakeword / faster-whisper / anthropic
- [ ] 写 voice_agent.py（VAD 录音 + Whisper + Claude）
- [ ] manager.py 加 voice 服务
- [ ] 端到端测试

**Phase 4 — 鉴权** (~30 分钟)
- [ ] 生成 internal_api_key
- [ ] server.py 中间件
- [ ] Pi 端 ble_service POST 带 token
- [ ] voice_agent POST 带 token

**Phase 5 — 增强** (long-term)
- [ ] 训练自定义唤醒词（"宝宝日记"）
- [ ] Claude 主动 TTS 提醒（"该喂奶了"）
- [ ] 多麦克风（婴儿房 + 客厅）

---

## 12. 参考实现

- [ReSpeaker Mic Array v2.0 (XVF3000) Wiki](https://wiki.seeedstudio.com/ReSpeaker_Mic_Array_v2.0/)
- [openWakeWord](https://github.com/dscripka/openWakeWord) — 唤醒词
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — STT
- [Claude API tool use 文档](https://docs.claude.com/en/docs/agents-and-tools/tool-use/overview)
- [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
- [systemd unit 文档](https://www.freedesktop.org/software/systemd/man/systemd.unit.html)
