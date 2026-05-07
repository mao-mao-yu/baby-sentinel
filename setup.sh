#!/usr/bin/env bash
# BabySentinel setup script (macOS / Linux)
# Usage: bash setup.sh          # core setup only
#        bash setup.sh --voice  # also install Voice Service deps (Whisper + TTS)

set -e

VOICE=0
for arg in "$@"; do
  [[ "$arg" == "--voice" ]] && VOICE=1
done

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

green()  { echo -e "\033[32m   OK  $*\033[0m"; }
yellow() { echo -e "\033[33m   !!  $*\033[0m"; }
red()    { echo -e "\033[31m   ERR $*\033[0m"; exit 1; }
step()   { echo -e "\n\033[36m>> $*\033[0m"; }

echo ""
echo "  BabySentinel 安装程序 (macOS/Linux)"
echo "  ─────────────────────────────────"

# ── 1. Python 版本 ────────────────────────────────────────────────────
step "检查 Python 版本"
PY=$(command -v python3 || command -v python || true)
[[ -z "$PY" ]] && red "未找到 python3，请先安装 Python 3.11+"
VER=$($PY --version 2>&1)
MINOR=$(echo "$VER" | sed -E 's/Python 3\.([0-9]+).*/\1/')
[[ "$MINOR" -lt 11 ]] && red "需要 Python 3.11+，当前: $VER"
green "$VER"

# ── 2. 虚拟环境 ───────────────────────────────────────────────────────
step "创建虚拟环境 (venv)"
if [[ -f "venv/bin/python" ]]; then
    green "已存在，跳过"
else
    $PY -m venv venv
    green "venv 已创建"
fi
PY="./venv/bin/python"
PIP="./venv/bin/pip"

# ── 3. Python 依赖 ────────────────────────────────────────────────────
step "安装 Python 依赖"
$PIP install --upgrade pip -q
$PIP install -r requirements.txt
green "核心依赖安装完成"

# ── 4. go2rtc ─────────────────────────────────────────────────────────
step "检查 go2rtc"
mkdir -p bin
GO2RTC="bin/go2rtc"
if [[ -f "$GO2RTC" ]]; then
    green "已存在: $GO2RTC"
else
    yellow "未找到 $GO2RTC，正在从 GitHub 下载..."
    ARCH=$(uname -m)
    if [[ "$ARCH" == "arm64" ]]; then
        URL="https://github.com/AlexxIT/go2rtc/releases/latest/download/go2rtc_mac_arm64"
    else
        URL="https://github.com/AlexxIT/go2rtc/releases/latest/download/go2rtc_mac_amd64"
    fi
    if curl -fsSL "$URL" -o "$GO2RTC"; then
        chmod +x "$GO2RTC"
        green "go2rtc 下载完成 ($ARCH)"
    else
        yellow "下载失败，请手动下载: $URL"
        yellow "并放置到: $ROOT/bin/go2rtc  然后 chmod +x bin/go2rtc"
    fi
fi

# 将路径写入 config.json（仅当 go2rtc_path 为空时更新）
if [[ -f "config.json" && -f "$GO2RTC" ]]; then
    "$PY" - <<'PYEOF'
import json
with open("config.json", encoding="utf-8") as f: c = json.load(f)
if not c.get("go2rtc_path"):
    c["go2rtc_path"] = "bin/go2rtc"
    with open("config.json", "w", encoding="utf-8") as f: json.dump(c, f, indent=2, ensure_ascii=False)
    print("   !!  config.json: go2rtc_path → bin/go2rtc")
PYEOF
fi

# ── 5. ffmpeg ─────────────────────────────────────────────────────────
step "检查 ffmpeg (下载到 bin/)"
FFMPEG_BIN="bin/ffmpeg"
if [[ -f "$FFMPEG_BIN" ]]; then
    green "已存在: $FFMPEG_BIN"
else
    yellow "未找到 $FFMPEG_BIN，正在从 evermeet.cx 下载静态构建..."
    ARCH=$(uname -m)
    # evermeet.cx 提供 macOS 静态构建（arm64 / x86_64 均为同一端点）
    FF_URL="https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip"
    TMP=$(mktemp /tmp/ffmpeg_XXXXXX.zip)
    if curl -fsSL --max-time 120 "$FF_URL" -o "$TMP" && \
       unzip -o "$TMP" ffmpeg -d bin/ >/dev/null 2>&1; then
        chmod +x "$FFMPEG_BIN"
        rm -f "$TMP"
        green "ffmpeg 下载完成 ($ARCH)"
    else
        rm -f "$TMP"
        yellow "静态下载失败，尝试 Homebrew..."
        if command -v brew &>/dev/null; then
            brew install ffmpeg
            BREW_FF=$(command -v ffmpeg)
            cp "$BREW_FF" bin/ffmpeg && chmod +x bin/ffmpeg
            green "ffmpeg 已从 Homebrew 复制到 bin/"
        else
            yellow "请安装 ffmpeg 并手动复制到 bin/ffmpeg"
        fi
    fi
fi

# 将路径写入 config.json（仅当 ffmpeg_path 为空时更新）
if [[ -f "config.json" && -f "$FFMPEG_BIN" ]]; then
    "$PY" - <<'PYEOF'
import json
with open("config.json", encoding="utf-8") as f: c = json.load(f)
if not c.get("ffmpeg_path"):
    c["ffmpeg_path"] = "bin/ffmpeg"
    with open("config.json", "w", encoding="utf-8") as f: json.dump(c, f, indent=2, ensure_ascii=False)
    print("   !!  config.json: ffmpeg_path → bin/ffmpeg")
PYEOF
fi

# ── 6. 配置文件 ───────────────────────────────────────────────────────
step "初始化配置文件"
if [[ -f "config.json" ]]; then
    green "config.json 已存在，跳过"
else
    cp config.example.json config.json
    green "已从 config.example.json 复制 → config.json"
fi

# Per-service config: 各服务首启时也会自动 fallback，但提前 copy 一份方便用户预编辑
for svc in ble recorder voice web; do
    src="services/$svc/config.example.json"
    dst="services/$svc/config.json"
    if [[ -f "$dst" ]]; then
        green "services/$svc/config.json 已存在，跳过"
    elif [[ -f "$src" ]]; then
        cp "$src" "$dst"
        green "已复制 services/$svc/config.example.json → config.json"
    fi
done

yellow "请编辑配置填写必填项:"
yellow "  config.json:                       tapo_rtsp、baby.birth_date"
yellow "  services/ble/config.json:          ble_address  (扫描: ./venv/bin/python tools/scan.py)"
yellow "  services/voice/config.json:        minimax_api_key 或 deepseek_api_key（如启用语音）"

# ── 7. 目录结构 ───────────────────────────────────────────────────────
step "创建运行时目录"
mkdir -p logs recordings
green "logs/  recordings/"

# ── 8. Voice Service deps (optional, pass --voice) ───────────────────
step "语音助手依赖 (Voice Service)"
if [[ "$VOICE" -eq 1 ]]; then
    ARCH=$(uname -m)
    if [[ "$(uname)" == "Darwin" && "$ARCH" == "arm64" ]]; then
        yellow "检测到 Apple Silicon，安装 mlx-whisper 替代 faster-whisper …"
        # Install everything except faster-whisper; add mlx-whisper
        $PIP install fastapi "uvicorn[standard]" python-multipart httpx websockets edge-tts librosa soundfile
        $PIP install mlx-whisper
        green "mlx-whisper 及 TTS 依赖安装完成 (Apple Silicon)"
    else
        $PIP install -r services/voice/requirements.txt
        green "Voice Service 依赖安装完成"
        yellow "如需 GPU (CUDA) 推理，请先安装 CUDA PyTorch:"
        yellow "  https://pytorch.org/get-started/locally/"
    fi
else
    green "跳过（如需安装，重新运行: bash setup.sh --voice）"
fi

# ── 9. 配对提示 ───────────────────────────────────────────────────────
step "Sense-U 配对"
if [[ -f "baby_code.json" ]]; then
    green "baby_code.json 已存在，无需重新配对"
else
    yellow "尚未配对，首次运行前请执行:"
    yellow "  ./venv/bin/python tools/pairing.py"
fi

# ── 完成 ──────────────────────────────────────────────────────────────
echo ""
echo -e "\033[32m  安装完成！\033[0m"
echo ""
echo "  启动方式:"
echo "    ./venv/bin/python manager.py                       # 管理界面 http://localhost:9091"
echo "    ./venv/bin/python services/web/server.py                    # 仅主服务 http://localhost:8080"
echo "    ./venv/bin/python services/voice/voice_service.py  # 语音服务 http://localhost:8001  (需 --voice)"
echo ""
echo "  语音服务（HTTP，自带客户端）:"
echo "    1. 运行 bash setup.sh --voice              安装 Whisper/TTS 依赖"
echo "    2. 编辑 services/voice/config.json         填写 llm_provider、minimax_api_key 或 deepseek_api_key 等"
echo "    3. 启动 services/voice/voice_service.py    （本机，服务端）"
echo "    4. POST WAV 到 /voice/process                 自带客户端（Pi/手机/任何设备）"
echo ""
