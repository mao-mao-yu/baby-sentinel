# BabySentinel 安装脚本 (Windows PowerShell)
# 用法: .\setup.ps1
# 可选: .\setup.ps1 -WithCry   # 同时安装哭声检测依赖

param([switch]$WithCry)

$ErrorActionPreference = "Stop"

function Write-Step($msg)  { Write-Host "`n>> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host "   OK  $msg" -ForegroundColor Green }
function Write-Warn($msg)  { Write-Host "   !!  $msg" -ForegroundColor Yellow }
function Write-Fail($msg)  { Write-Host "   ERR $msg" -ForegroundColor Red; exit 1 }

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ROOT

Write-Host ""
Write-Host "  BabySentinel 安装程序" -ForegroundColor White
Write-Host "  ─────────────────────" -ForegroundColor DarkGray

# ── 1. Python 版本 ────────────────────────────────────────────────────
Write-Step "检查 Python 版本"
try {
    $ver = python --version 2>&1
    if ($ver -match "Python (\d+)\.(\d+)") {
        $major, $minor = [int]$Matches[1], [int]$Matches[2]
        if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 11)) {
            Write-Fail "需要 Python 3.11+，当前: $ver"
        }
        Write-Ok $ver
    } else {
        Write-Fail "无法识别 Python 版本: $ver"
    }
} catch {
    Write-Fail "未找到 python，请先安装 Python 3.11+"
}

# ── 2. 虚拟环境 ───────────────────────────────────────────────────────
Write-Step "创建虚拟环境 (venv)"
if (Test-Path "venv\Scripts\python.exe") {
    Write-Ok "已存在，跳过"
} else {
    python -m venv venv
    Write-Ok "venv 已创建"
}
$PIP = ".\venv\Scripts\pip.exe"

# ── 3. 安装 Python 依赖 ───────────────────────────────────────────────
Write-Step "安装 Python 依赖"
& $PIP install --upgrade pip -q
& $PIP install -r requirements.txt
Write-Ok "核心依赖安装完成"

if ($WithCry) {
    Write-Step "安装哭声检测依赖 (tensorflow ~2 GB，耗时较长)"
    & $PIP install -r requirements-cry.txt
    Write-Ok "哭声检测依赖安装完成"
}

# ── 4. go2rtc ─────────────────────────────────────────────────────────
Write-Step "检查 go2rtc"
$go2rtcPath = "bin\go2rtc.exe"
if (Test-Path $go2rtcPath) {
    Write-Ok "已存在: $go2rtcPath"
} else {
    Write-Warn "未找到 bin\go2rtc.exe，正在从 GitHub 下载..."
    New-Item -ItemType Directory -Force bin | Out-Null
    $url = "https://github.com/AlexxIT/go2rtc/releases/latest/download/go2rtc_win64.exe"
    try {
        Invoke-WebRequest -Uri $url -OutFile $go2rtcPath -UseBasicParsing
        Write-Ok "go2rtc 下载完成"
    } catch {
        Write-Warn "下载失败: $_"
        Write-Warn "请手动下载: $url"
        Write-Warn "并放置到: $ROOT\bin\go2rtc.exe"
    }
}

# ── 5. ffmpeg ─────────────────────────────────────────────────────────
Write-Step "检查 ffmpeg"
$ffmpegInPath = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($ffmpegInPath) {
    Write-Ok "已在 PATH: $($ffmpegInPath.Source)"
    Write-Warn "提示: config.json 中 ffmpeg_path 留空即可自动使用"
} else {
    Write-Warn "未在 PATH 中找到 ffmpeg"
    Write-Warn "请下载 ffmpeg 并在 config.json 的 ffmpeg_path 中填写完整路径"
    Write-Warn "下载: https://github.com/BtbN/FFmpeg-Builds/releases"
}

# ── 6. 配置文件 ───────────────────────────────────────────────────────
Write-Step "初始化配置文件"
if (Test-Path "config.json") {
    Write-Ok "config.json 已存在，跳过"
} else {
    Copy-Item "config.example.json" "config.json"
    Write-Ok "已从 config.example.json 复制 → config.json"
    Write-Warn "请编辑 config.json 填写以下必填项:"
    Write-Warn "  ble_address         Sense-U 蓝牙地址 (工具: tools\scan_ble.py)"
    Write-Warn "  tapo_rtsp           摄像头 RTSP 地址"
    Write-Warn "  baby.birth_date     宝宝生日 (YYYYMMDD)"
}

# ── 7. 目录结构 ───────────────────────────────────────────────────────
Write-Step "创建运行时目录"
@("logs", "recordings", "bin") | ForEach-Object {
    New-Item -ItemType Directory -Force $_ | Out-Null
}
Write-Ok "logs/  recordings/  bin/"

# ── 8. 配对提示 ───────────────────────────────────────────────────────
Write-Step "Sense-U 配对"
if (Test-Path "baby_code.json") {
    Write-Ok "baby_code.json 已存在，无需重新配对"
} else {
    Write-Warn "尚未配对，首次运行前请执行:"
    Write-Warn "  .\venv\Scripts\python.exe tools\pairing.py"
}

# ── 完成 ──────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  安装完成！" -ForegroundColor Green
Write-Host ""
Write-Host "  启动方式:" -ForegroundColor White
Write-Host "    .\venv\Scripts\python.exe manager.py   # 管理界面 http://localhost:9091" -ForegroundColor DarkGray
Write-Host "    .\venv\Scripts\python.exe server.py    # 仅主服务 http://localhost:8080" -ForegroundColor DarkGray
Write-Host ""
