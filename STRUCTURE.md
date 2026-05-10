# BabySentinel — 项目结构

> 一台 Mac 跑全部后端 + 浏览器 UI；Pi 只跑独立的 BLE 适配（[sense-u-ble](https://github.com/...)）+ 可选音频转流。
> 摄像头走 Tapo C200 RTSP → go2rtc → WebRTC，传感器走 sense-u-ble 蓝牙读取 → manager 这边 HTTP 拉。

```
baby-sentinel/
├── manager.py                 # 总管入口（:9091）— supervisor + config admin + 服务控制
├── backend/
│   ├── shared/                # 真正跨多个服务共用的 3 个模块
│   │   ├── config.py            # config.json 加载 / BASE_DIR / log 配置
│   │   ├── sensors_db.py        # SQLite 传感器时序读写
│   │   └── video_util.py        # mp4 完整性 probe
│   └── services/
│       ├── web/               # 主 web 服务（:8080）— FastAPI + WebSocket
│       │   ├── server.py        # FastAPI app 入口；REST + WS + alert + baby_log
│       │   ├── config.py        # 从 ROOT_CFG / 本地 config.json 读取 web 字段
│       │   ├── state.py         # 全局可变状态（active_ws / sensor_state / alert_log）
│       │   ├── go2rtc_monitor.py # go2rtc HTTP 健康监测 + dead/stall 自愈
│       │   ├── alerts.py        # 告警分发（Discord / BARK / QQ stub）
│       │   ├── i18n.py          # 后端翻译（zh/ja）+ posture / entry_type 标签
│       │   ├── baby_log.py      # 育儿日志 CRUD + 喂奶倒计时 + 当日统计
│       │   ├── notify/          # 通知通道实现
│       │   │   ├── _http.py       # 同步 + 异步 urllib 包装
│       │   │   ├── discord_send.py  # 同步 webhook 发送
│       │   │   ├── discord_bot.py   # Gateway 客户端 + Slash Command
│       │   │   └── bark_send.py     # iOS BARK 推送
│       │   └── static/
│       │       ├── images/        # 5 张姿势 PNG（supine/prone/left_side/right_side/sitting）
│       │       │                  #   被 SensorPanel.tsx 通过 /static/images/${enum}.png 引用
│       │       ├── web-dist/      # frontend/baby-sentinel-web 构建产物（gitignored）
│       │       └── manager-dist/  # frontend/manager 构建产物（gitignored）
│       ├── recorder/          # 视频录像服务（独立进程，无端口）
│       │   ├── service.py       # ffmpeg 分段录制 + 残缺 mp4 清理 + 传感器存档
│       │   ├── config.py        # 录像目录 / 分段时长 / ffmpeg 路径
│       │   └── config.example.json
│       └── voice/             # 语音服务（:8001）— Whisper STT + LLM + TTS
│           ├── service.py       # FastAPI 入口；POST /voice/process / /voice/test_llm
│           ├── config.py        # 后端选型 / 鉴权 / 录音参数
│           ├── stt.py           # mlx-whisper / openai whisper
│           ├── llm/             # LLM provider 抽象
│           │   ├── base.py        # LLMProvider 接口
│           │   ├── deepseek.py    # DeepSeek chat
│           │   ├── minimax.py     # MiniMax chat
│           │   └── agent.py       # tool-calling 主循环
│           ├── tts/             # TTS provider 抽象
│           │   ├── base.py
│           │   ├── edge.py        # microsoft-edge-tts（免费）
│           │   └── minimax.py     # MiniMax T2A v2
│           └── tools/           # LLM function-calling 工具集
│               └── baby_records.py  # 喂奶 / 尿布 / 睡眠等记录工具
├── frontend/
│   ├── baby-sentinel-web/     # 主 UI（React + Vite + shadcn/ui）
│   │   └── src/
│   │       ├── App.tsx          # 根组件 + 路由（/ vs /playback）+ Provider 链
│   │       ├── main.tsx         # ReactDOM.createRoot 入口
│   │       ├── theme.tsx        # 浅 / 深主题 Provider + useTheme
│   │       ├── config-ui.ts     # 传感器阈值前端 fallback（真值在 manager config）
│   │       ├── api/
│   │       │   ├── ws.tsx         # WebSocket 客户端 + Provider + 多 select hook
│   │       │   └── manager-config.ts  # /api/manager/config GET 包装
│   │       ├── i18n/index.tsx   # zh/ja 字典 + LangProvider + useT()
│   │       ├── components/
│   │       │   ├── Header.tsx     # 顶栏 + 服务状态 pill + 主题切换
│   │       │   ├── SensorPanel.tsx # 呼吸 / 体温 / 姿势卡片 + 状态行
│   │       │   ├── CameraView.tsx # WebRTC <video> 接 go2rtc /api/webrtc
│   │       │   ├── AlertBanner.tsx # 顶部告警条
│   │       │   ├── AlertDialog.tsx # 告警弹窗 + dismiss
│   │       │   ├── MobileTabs.tsx # 手机端 3-tab 切换
│   │       │   └── ui/            # shadcn/ui 原语（button / dialog / select 等）
│   │       ├── baby-log/        # 育儿日志整体功能区
│   │       │   ├── Panel.tsx      # 容器（DateNav + DateStats + Quick + TodayList）
│   │       │   ├── QuickButtons.tsx # 喂奶 / 尿布 / 睡眠快捷按钮
│   │       │   ├── pickers.tsx    # 配方奶 / 母乳 / 便便等弹窗 picker
│   │       │   ├── DrumPicker.tsx # 滚轮选择器（时间 / 数字）
│   │       │   ├── EditDialog.tsx # 已有记录编辑 / 删除
│   │       │   ├── FeedCountdown.tsx # 下次喂奶倒计时
│   │       │   ├── TodayList.tsx  # 当日已记录列表
│   │       │   ├── DateNav.tsx    # 日期前后切换 + "今天" tag
│   │       │   ├── DateStats.tsx  # 当日统计胶囊
│   │       │   ├── api.ts         # baby_log REST 调用
│   │       │   ├── scope.tsx      # BabyLogScopeProvider（当前查询日期）
│   │       │   ├── stats.ts       # 客户端统计计算
│   │       │   ├── format.ts      # 时间 / 单位格式化
│   │       │   ├── constants.ts   # 选项枚举常量
│   │       │   └── types.ts       # entry / stats 类型
│   │       ├── playback/        # 录像回放页（/playback 路由命中）
│   │       │   ├── Page.tsx       # 4 数据源协调（dates/segs/sensors/events）
│   │       │   ├── VideoPanel.tsx # <video> 段播放 + 时间码叠加
│   │       │   ├── Timeline.tsx   # 24h 时间轴 + 拖动 scrub + event/segment 标记
│   │       │   ├── QuickJumps.tsx # ⏮ ⬅ ➡ ⏭ + ±h 跳转
│   │       │   ├── api.ts
│   │       │   ├── utils.ts       # ts 格式化 / 二分查传感器 / event icon
│   │       │   └── types.ts
│   │       ├── types/wire.ts    # WS 帧 / sensor / alert 类型（与后端对齐）
│   │       ├── lib/utils.ts     # cn() classname 合并
│   │       ├── index.css        # Tailwind v4 + theme tokens
│   │       └── vite-env.d.ts
│   └── manager/               # 管理 UI（React + Vite + shadcn/ui）
│       └── src/
│           ├── App.tsx          # 服务卡片网格 + 告警同步 + 顶栏
│           ├── main.tsx
│           ├── config-schema.ts # 全局 + 各服务字段定义（编辑器渲染依据）
│           ├── api/manager.ts   # /api/manager/* 调用
│           ├── i18n/index.tsx
│           ├── components/
│           │   ├── ServiceCard.tsx # 单个服务卡（start/stop/restart/log/gear）
│           │   ├── ConfigDialog.tsx # 字段表单 + dotted-path 写回
│           │   ├── PairDialog.tsx   # BLE 配对引导
│           │   └── ui/            # shadcn/ui 原语
│           ├── lib/{utils,path}.ts
│           ├── types/manager.ts # services / status / log shape
│           └── index.css
├── scripts/
│   ├── pi_streamer.sh         # Pi 端 ReSpeaker 音频转 RTSP（推到 mediamtx）
│   └── test_llm.py            # 跳过 STT/TTS 直发文本到 voice service 调试 LLM
├── docs/                      # 设计文档（gitignored，仅本地）
├── recordings/                # ffmpeg 输出（gitignored）
├── logs/                      # SQLite + 协议日志（gitignored）
├── bin/                       # go2rtc / ffmpeg 二进制（gitignored，平台相关）
├── config.json                # 真实配置（gitignored）
├── config.example.json        # 模板
├── go2rtc.yaml                # manager 启动时由 _gen_go2rtc_yaml 生成
├── baby_code.json             # Sense-U 配对密钥（gitignored）
├── requirements.txt
├── pyrightconfig.json         # extraPaths=['backend']
├── setup.sh / setup.ps1       # 首次安装
└── README.md
```

## 服务进程与端口

| Service     | 进程入口                                    | 端口 | 备注 |
|-------------|---------------------------------------------|------|------|
| **manager** | `manager.py`                                | 9091 | supervisor + config admin + 服务控制 |
| **server**  | `backend/services/web/server.py`            | 8080 | 主 web API + WebSocket，前端 SPA 这里挂 |
| **recorder**| `backend/services/recorder/service.py`      | —    | ffmpeg 分段录制 + 传感器时序入库 |
| **voice**   | `backend/services/voice/service.py`         | 8001 | Whisper STT + LLM (DeepSeek/MiniMax) + TTS |
| **go2rtc**  | `bin/go2rtc -config go2rtc.yaml`            | 1984 | RTSP → WebRTC 桥；yaml 由 manager 生成 |
| **ble**     | `bin/sense-u-ble`（**Pi 上独立项目**，HTTP 远端） | 8082 | manager 通过 SSH 远程控制 |

服务子进程都靠同一招把 import 路径打通：

```python
# 每个 service.py / server.py 顶部
sys.path.insert(0, str(Path(__file__).parent.parent.parent))   # → backend/
from shared.X import ...
from services.X.Y import ...
```

`manager.py` 在根但走相同 idiom：

```python
sys.path.insert(0, str(Path(__file__).parent / "backend"))
from shared.config import ROOT_CFG
```

## 配置流转

```
config.json (root, gitignored)
   │
   ├─→ shared/config.py 加载 → ROOT_CFG (dict)
   │       │
   │       └─→ 每个 service 的 config.py 从 ROOT_CFG 读关心字段
   │             并用 backend/services/X/config.json (gitignored) 做 service 私有覆写
   │
   └─→ /api/manager/config (manager.py) ←  manager UI / web UI 读
                              ↑
                              └─ POST 写回；改完用户在 service card 点重启
```

字段编辑入口：
- **manager UI 顶栏齿轮** → 全局字段（语言 / alert / discord / bark / pi / 传感器阈值 / 宝宝信息）
- **每个服务卡片齿轮** → 该服务独占字段（端口 / 各 provider 选型 / 录像分段时长 等）

## 前端构建产物

```
frontend/baby-sentinel-web/  ──vite build──→  backend/services/web/static/web-dist/
frontend/manager/            ──vite build──→  backend/services/web/static/manager-dist/
```

两个目录都 gitignored。`web-dist/` 由 server.py（:8080）的 `/` 路由直接 serve，`manager-dist/` 由 manager.py（:9091）的 `/` 路由 serve。两边都通过同一 `/static` mount 暴露 asset 文件夹。

## WebSocket 帧约定

`backend/services/web/state.py:broadcast()` → 前端 `frontend/baby-sentinel-web/src/api/ws.tsx`。

| `type`            | 用途                                |
|-------------------|-------------------------------------|
| `state`           | 初始全量快照（连接握手）            |
| `sensor`          | 实时传感器（呼吸 / 体温 / 姿势 / cam_ok / ble_ok） |
| `baby_stats`      | 喂奶 / 尿布 / 睡眠当日统计 + 推荐量 |
| `alert`           | 新告警（弹 banner）                 |
| `alert_active`    | 当前活跃告警列表（同步初始 + 更新）  |
| `alert_dismissed` | 某条告警被 dismiss                  |

类型定义在 `frontend/baby-sentinel-web/src/types/wire.ts`，跟后端 broadcast payload 对齐。

## 命名约定

- **目录**：kebab-case（如 `baby-log`、`baby-sentinel-web`）
- **Python 模块/文件**：snake_case（如 `baby_log.py`、`go2rtc_monitor.py`）
- **React 组件文件**：PascalCase（`Header.tsx`、`CameraView.tsx`）
- **TS 工具/类型/api**：camelCase 或 kebab-case（`utils.ts`、`manager-config.ts`、`config-schema.ts`）
- **服务入口统一叫 `service.py`**（recorder / voice），主 web 服务因为是 FastAPI 起家叫 `server.py`
- **跨服务共用** → `backend/shared/`；**单个服务用** → `backend/services/<svc>/`
