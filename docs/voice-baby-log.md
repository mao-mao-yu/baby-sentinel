# 语音育儿日记设计书

> 把宝宝旁边的麦克风变成"听一句话就记一条 log"的入口。
> 「喂了 80 毫升配方奶」「拉便便了」之类的指令一句话搞定，无需开 App。

## 目标

- **零交互**：唤醒词 → 说一句 → 自动写入 baby_log，无需打开手机
- **隐私优先**：录音不出门；只有转录后的文本（短）发给云端 LLM
- **延迟 < 2s**：从话音落下到 TTS 反馈"已记录"
- **复用现有 baby_log REST API**，不另起一套写入路径

## 整体架构

```
┌────────────────────── 婴儿房 ──────────────────────┐
│                                                    │
│   麦克风（USB / Wi-Fi）                             │
│         ↓ 音频流                                    │
│                                                    │
└────────────────────────────────────────────────────┘
                         │ USB 直连 / Wi-Fi RTP / Pi 中继
                         ▼
┌────────────────────── Mac mini ────────────────────┐
│                                                    │
│  ① openWakeWord  ← 始终运行，CPU 1~2%              │
│         ↓ 检测到唤醒词                              │
│                                                    │
│  ② faster-whisper STT  ← 录 ~5s 后停止               │
│         ↓ 文本                                      │
│                                                    │
│  ③ Claude Haiku 4.5 + tool_use                     │
│         ↓ tool_call: log_baby                      │
│                                                    │
│  ④ POST /api/log  ← 本地，鉴权 token                │
│         ↓                                           │
│  ⑤ SQLite baby_log                                 │
│         ↓                                           │
│  ⑥ TTS "已记录" 反馈（可选，本地 say 命令）           │
│                                                    │
└────────────────────────────────────────────────────┘
```

只有第 ③ 步出网。第 ②④⑤⑥ 全部本地。

## 麦克风选型

考虑因素：
- **拾音距离**：婴儿房一般 3~4m，说话人可能在床边、换尿布台、门口
- **降噪**：白噪音机、风扇、有时宝宝哭——需要降噪 / 波束成形
- **24/7 稳定性**：USB 远比蓝牙稳
- **延迟**：USB ~10ms，蓝牙 100~300ms，Wi-Fi 200ms~

| 型号 | 价格 | 远场 | 降噪 | 接口 | 推荐度 |
|---|---|---|---|---|---|
| **ReSpeaker USB Mic Array v2.0**（Seeed） | ~¥500-700 | 5m | 4 麦阵列 + 板载 DSP 波束成形 + AEC + DOA | USB | **⭐ 首选** |
| ReSpeaker 4-Mic Linear Array | ~¥300 | 3m | 4 麦阵列，无 DSP 需自己跑 | USB | 折中 |
| Anker PowerConf S3 | ~¥800-1200 | 4m | 全向 + AEC（会议麦） | USB | 偏贵 |
| Jabra Speak 410 | ~¥600-800 | 3m | 全向 + AEC | USB | OK |
| 普通会议全向麦（如 MAONO） | ~¥150-300 | 2m | 弱 | USB | 预算极限 |
| AirPods / 蓝牙耳机 | - | 1m | 不行（HFP 8 kHz） | 蓝牙 | ❌ 不推荐 |

### 首选：ReSpeaker USB Mic Array v2.0

理由：
- 4 麦克风圆形阵列，**波束成形**自动对准声源，宝宝睡觉时小声说话也能拾到
- 板载 XMOS DSP，硬件做 AEC（消除自己 TTS 的回声）+ 降噪
- DOA（声源定向）输出，可以拒绝来自摄像头方向（白噪音机）的声音
- 即插即用 UAC（USB Audio Class），macOS / Linux 免驱
- 在 Home Assistant / openWakeWord / Rhasspy 社区是默认推荐
- Seeed 官方 $79，淘宝代购 ¥500-700

### 安装位置

放在距离换尿布台/床边 1.5~2m 的高处（架子顶或墙挂），**不要**放在白噪音机旁边。USB 线尽量短（< 5m），太长用 USB 有源延长。

## 蓝牙连接 Mac mini 是否可行

**技术上能用，但强烈不推荐**。原因：

### 1. 蓝牙音频协议本身带宽差

蓝牙音频有两个 profile：
- **A2DP**（高质量音乐流）—— **只有播放方向**，蓝牙耳机播音用的，不能用作 mic input
- **HFP / HSP**（电话听筒模式）—— 双向，但 **mic 通道只有 8 kHz / 16 kHz，单声道，强压缩**

Whisper 训练数据是 16 kHz，HFP 16 kHz 勉强能用，但**降噪空间极小、远场拾音几乎丧失**。

### 2. 24/7 稳定性差

蓝牙连接墙后、距离 > 5m、电池低、Mac mini 同时蓝牙鼠键……都会断连。断了不会自动恢复，需要手动重连。**婴儿监控就是要稳定**。

### 3. macOS 蓝牙总线拥挤

Mac mini 蓝牙总线还要给磁吸键盘 / Magic Mouse / AirPods 用。同时跑高带宽 mic 流容易抢资源。

### 4. 推荐替代

如果**实在**需要无线（不想拉线）：
- **Wi-Fi 麦克风方案**：`M5Stack Atom Echo` 或 `ESP32-S3 + INMP441` 跑 ESPHome，把音频流通过 RTP/UDP 发给 Mac mini。约 ¥150 一个，延迟 ~200ms，断网会自动重连
- **本地中继方案**：Pi Zero 2W (~¥200) + USB 麦 → 通过 Wi-Fi 把音频流给 Mac mini。Pi 上跑唤醒词省 Mac 的 CPU
- **简单粗暴**：USB 延长线 5~10m + ReSpeaker，最稳

## 核心组件选型

### 唤醒词：openWakeWord
- 开源，可训练自定义唤醒词（"宝宝日记""嘿宝宝"）
- 在 Mac mini M2 / 树莓派 4B 都能跑，CPU 1~2%
- 延迟 < 200ms
- 训练 5 分钟自己的声音 1 个小时 GPU/Colab 出一个 model

### STT：faster-whisper（CTranslate2 加速 Whisper）
- 支持中/日/英多语言（混说也行）
- Mac mini M2 上 `small` 模型识别 5s 录音 < 1s
- `medium` 准确率更高但延迟翻倍
- 全程本地，**录音不出门**

### LLM：Claude Haiku 4.5
- tool_use 准确度好、速度快、便宜
- 单次调用 ~600ms，成本 ~$0.0004（每天 10 次约 **$0.40/月**）
- API 调用只发文本（"刚喂了 80ml 配方奶"），不发音频

### 数据库：SQLite（即将从 JSON 迁过来）
- baby_log.json → SQLite，单文件、零运维
- 写入需鉴权（X-API-Key），开放给本机的 voice agent 进程

### TTS 反馈（可选）
- macOS 自带 `say` 命令免费 + 即时
- 简短一句 "已记录配方奶 80 毫升" 即可

## API 鉴权（开放给 Claude tool_use 前提）

**必须做**，不然 LLM 调你 API 写宝宝日志这件事是裸奔的。

最简方案：
- [config.json](../config.json) 加一个 `internal_api_key`
- 现有 `/api/log` 系列加一层中间件检查 `X-API-Key` header
- voice agent 启动时读 config 里同一个 key
- 公开接口（websocket / 浏览器 UI）走另一个无鉴权 host:port

更稳的方案：
- 只让 voice agent 监听 `127.0.0.1`（本地回环），外部根本访问不到
- 加 token 是双保险

## tool definition for Claude

写好的 schema 直接发给 Claude API，它就能正确填字段：

```json
{
  "name": "log_baby_event",
  "description": "记录宝宝事件到育儿日志。仅当用户明确陈述发生了某事时才调用。",
  "input_schema": {
    "type": "object",
    "properties": {
      "type": {
        "type": "string",
        "enum": ["formula", "breastfeed", "bottle_milk",
                 "sleep", "wake", "wet", "poop",
                 "temp", "height", "weight", "bath", "pump"],
        "description": "事件类型"
      },
      "amount_ml": {"type": "number", "description": "奶量（mL），仅喂奶事件"},
      "duration_min": {"type": "number", "description": "持续时长（分钟），仅母乳/睡眠"},
      "side": {"type": "string", "enum": ["left", "right", "both"]},
      "value": {"type": "number", "description": "数值（°C/cm/g），仅 temp/height/weight"},
      "note": {"type": "string", "description": "其他文字备注"}
    },
    "required": ["type"]
  }
}
```

## 成本估算

| 项目 | 一次性 | 月度 |
|---|---|---|
| ReSpeaker Mic Array v2.0 | ~¥500-700 | - |
| Mac mini（已有） | - | - |
| Claude Haiku API | - | **~$0.4 / 月**（按每天 10 次记录估算） |
| openWakeWord / faster-whisper / SQLite | 0 | 0 |
| **合计** | **~¥600** | **约 ¥3 / 月** |

## 端到端延迟分解

| 阶段 | 耗时 |
|---|---|
| 唤醒词检测（说完 → 检测到） | ~200ms |
| 录音（用户说话时长，平均） | ~3000ms |
| VAD 判定结束 | ~300ms |
| Whisper STT 转录 | ~800ms |
| Claude API tool_use 推理 | ~600ms |
| 本地 POST /api/log | ~50ms |
| TTS "已记录" | ~300ms（异步，不计入感知延迟） |
| **从话音落下到反馈** | **~1.7s** |

## 实施分阶段

### Phase 1（最小可用）
1. baby_log 从 JSON 迁到 SQLite（独立任务，已规划）
2. 现有 `/api/log` 加 `X-API-Key` 鉴权
3. 写一个独立 `voice_agent.py` 进程：USB 麦 → openWakeWord → whisper → Claude API → POST /api/log
4. 跑在 Mac mini 上，纯命令行调试

### Phase 2（生产可用）
5. 接 ReSpeaker Mic Array，调整波束成形 + 降噪参数
6. 加 macOS `say` TTS 反馈
7. 把 voice_agent 加进 manager.py 的 SERVICES，统一管理 / 自启 / 看日志

### Phase 3（增强）
8. 自定义唤醒词（"宝宝日记"或宝宝小名）
9. 反向方向：从 Claude 主动播报（"该喂奶了"通过 TTS 而不是 Discord 推送）
10. 多麦克风（婴儿房 + 客厅 + 厨房）

## 不做的事

- **不做云端 STT**：录音不出门是底线
- **不做本地 LLM**：tool_use 准确率 / 中日双语理解，本地小模型还差太远
- **不做蓝牙麦**：上面已经详述
- **不做唤醒词以外的语义检测**（VAD always-on）：误触发太多，也不省事

## 参考实现

- [openWakeWord](https://github.com/dscripka/openWakeWord)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [ReSpeaker USB Mic Array v2.0 文档](https://wiki.seeedstudio.com/ReSpeaker_Mic_Array_v2.0/)
- [Claude API tool use](https://docs.claude.com/en/docs/agents-and-tools/tool-use/overview)
