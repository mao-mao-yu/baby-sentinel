# BabySentinel setup script (Windows PowerShell)
# Usage: .\setup.ps1

param()

$ErrorActionPreference = "Stop"

function Write-Step($msg)  { Write-Host "`n>> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host "   OK  $msg" -ForegroundColor Green }
function Write-Warn($msg)  { Write-Host "   !!  $msg" -ForegroundColor Yellow }
function Write-Fail($msg)  { Write-Host "   ERR $msg" -ForegroundColor Red; exit 1 }

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ROOT

Write-Host ""
Write-Host "  BabySentinel Setup" -ForegroundColor White
Write-Host "  ------------------" -ForegroundColor DarkGray

# ── 1. Python version ─────────────────────────────────────────────────
Write-Step "Checking Python version"
try {
    $ver = python --version 2>&1
    if ($ver -match "Python (\d+)\.(\d+)") {
        $major, $minor = [int]$Matches[1], [int]$Matches[2]
        if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 11)) {
            Write-Fail "Python 3.11+ required, found: $ver"
        }
        Write-Ok $ver
    } else {
        Write-Fail "Cannot detect Python version: $ver"
    }
} catch {
    Write-Fail "python not found. Please install Python 3.11+"
}

# ── 2. Virtual environment ────────────────────────────────────────────
Write-Step "Creating virtual environment (venv)"
if (Test-Path "venv\Scripts\python.exe") {
    Write-Ok "Already exists, skipping"
} else {
    python -m venv venv
    Write-Ok "venv created"
}
$PIP = ".\venv\Scripts\pip.exe"

# ── 3. Python dependencies ────────────────────────────────────────────
Write-Step "Installing Python dependencies"
& $PIP install --upgrade pip -q
& $PIP install -r requirements.txt
Write-Ok "Core dependencies installed"

# ── 4. go2rtc ─────────────────────────────────────────────────────────
Write-Step "Checking go2rtc"
$go2rtcPath = "bin\go2rtc.exe"
if (Test-Path $go2rtcPath) {
    Write-Ok "Already exists: $go2rtcPath"
} else {
    Write-Warn "Not found, downloading from GitHub..."
    New-Item -ItemType Directory -Force bin | Out-Null
    $url = "https://github.com/AlexxIT/go2rtc/releases/latest/download/go2rtc_win64.exe"
    try {
        Invoke-WebRequest -Uri $url -OutFile $go2rtcPath -UseBasicParsing
        Write-Ok "go2rtc downloaded"
    } catch {
        Write-Warn "Download failed: $_"
        Write-Warn "Please download manually: $url"
        Write-Warn "Place at: $ROOT\bin\go2rtc.exe"
    }
}

# Write go2rtc_path to config.json (only if currently empty)
if ((Test-Path "config.json") -and (Test-Path $go2rtcPath)) {
    $pyCode = @'
import json
with open("config.json", encoding="utf-8") as f: c = json.load(f)
if not c.get("go2rtc_path"):
    c["go2rtc_path"] = "bin/go2rtc.exe"
    with open("config.json", "w", encoding="utf-8") as f: json.dump(c, f, indent=2, ensure_ascii=False)
    print("   !!  config.json: go2rtc_path -> bin/go2rtc.exe")
'@
    $pyCode | & ".\venv\Scripts\python.exe"
}

# ── 5. ffmpeg ─────────────────────────────────────────────────────────
Write-Step "Checking ffmpeg (downloading to bin\)"
$ffmpegBin = "bin\ffmpeg.exe"
if (Test-Path $ffmpegBin) {
    Write-Ok "Already exists: $ffmpegBin"
} else {
    Write-Warn "Not found, downloading from GitHub..."
    $zipUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip"
    $zipTmp = "bin\ffmpeg-tmp.zip"
    try {
        Invoke-WebRequest -Uri $zipUrl -OutFile $zipTmp -UseBasicParsing
        Expand-Archive $zipTmp -DestinationPath "bin\ffmpeg-tmp" -Force
        $exe = Get-ChildItem "bin\ffmpeg-tmp" -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
        if ($exe) {
            Copy-Item $exe.FullName $ffmpegBin
            Write-Ok "ffmpeg downloaded"
        } else {
            Write-Warn "ffmpeg.exe not found in zip"
        }
    } catch {
        Write-Warn "Download failed: $_"
        Write-Warn "Please download manually: $zipUrl"
        Write-Warn "Extract ffmpeg.exe and place at bin\ffmpeg.exe"
    } finally {
        Remove-Item $zipTmp -ErrorAction SilentlyContinue
        Remove-Item "bin\ffmpeg-tmp" -Recurse -ErrorAction SilentlyContinue
    }
}

# Write ffmpeg_path to config.json (only if currently empty)
if ((Test-Path "config.json") -and (Test-Path $ffmpegBin)) {
    $pyCode = @'
import json
with open("config.json", encoding="utf-8") as f: c = json.load(f)
if not c.get("ffmpeg_path"):
    c["ffmpeg_path"] = "bin/ffmpeg.exe"
    with open("config.json", "w", encoding="utf-8") as f: json.dump(c, f, indent=2, ensure_ascii=False)
    print("   !!  config.json: ffmpeg_path -> bin/ffmpeg.exe")
'@
    $pyCode | & ".\venv\Scripts\python.exe"
}

# ── 6. Config file ────────────────────────────────────────────────────
Write-Step "Initializing config file"
if (Test-Path "config.json") {
    Write-Ok "config.json already exists, skipping"
} else {
    Copy-Item "config.example.json" "config.json"
    Write-Ok "Copied config.example.json -> config.json"
    Write-Warn "Please edit config.json and fill in:"
    Write-Warn "  ble_address         Sense-U BLE address (tool: tools\scan_ble.py)"
    Write-Warn "  tapo_rtsp           Camera RTSP URL"
    Write-Warn "  baby.birth_date     Baby's birthday (YYYYMMDD)"
}

# ── 7. Runtime directories ────────────────────────────────────────────
Write-Step "Creating runtime directories"
@("logs", "recordings", "bin") | ForEach-Object {
    New-Item -ItemType Directory -Force $_ | Out-Null
}
Write-Ok "logs/  recordings/  bin/"

# ── 8. Pairing reminder ───────────────────────────────────────────────
Write-Step "Sense-U pairing"
if (Test-Path "baby_code.json") {
    Write-Ok "baby_code.json exists, no re-pairing needed"
} else {
    Write-Warn "Not yet paired. Before first run, execute:"
    Write-Warn "  .\venv\Scripts\python.exe tools\pairing.py"
}

# ── Done ──────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "  Start with:" -ForegroundColor White
Write-Host "    .\venv\Scripts\python.exe manager.py   # Manager UI  http://localhost:9091" -ForegroundColor DarkGray
Write-Host "    .\venv\Scripts\python.exe server.py    # Main server http://localhost:8080" -ForegroundColor DarkGray
Write-Host ""
