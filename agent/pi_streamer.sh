#!/usr/bin/env bash
# Pi Audio Streamer — publishes ReSpeaker audio as RTSP via mediamtx.
#
# 编码：libopus 32 kbps mono，20ms 帧，lowdelay；UDP 传输。
# 服务端 go2rtc 直接做轨道路由（无转码），浏览器原生吃 Opus。
# 端到端延迟约 100~200ms（含 ALSA 采集 + 编码 + LAN + WebRTC 输出）。
#
# Prerequisites on Pi:
#   sudo apt install ffmpeg
#   # Download mediamtx binary from https://github.com/bluenviron/mediamtx/releases
#   # Place mediamtx in ~/mediamtx/ and create mediamtx.yml (see below)
#
# mediamtx.yml minimal config:
#   paths:
#     respeaker:
#       source: publisher
#
# This stream is then pulled by go2rtc on the server:
#   Set "pi_audio_rtsp": "rtsp://PI_IP:8554/respeaker" in config.json
#
# Usage:
#   bash agent/pi_streamer.sh
#   bash agent/pi_streamer.sh plughw:1,0    # override ALSA device

set -euo pipefail

ALSA_DEVICE="${1:-default}"     # PipeWire/PulseAudio default, or plughw:1,0 etc.
MEDIAMTX_URL="rtsp://localhost:8554/respeaker"
SAMPLE_RATE=48000               # Opus 内部强制 48 kHz；这里也用 48k 省一次重采样
CHANNELS=1                      # mono — 婴儿监控不需要立体声

echo "[pi_streamer] Input:  ALSA device='$ALSA_DEVICE' ${SAMPLE_RATE}Hz mono"
echo "[pi_streamer] Codec:  libopus 32k lowdelay frame=20ms"
echo "[pi_streamer] Output: $MEDIAMTX_URL  (UDP)"
echo "[pi_streamer] Press Ctrl+C to stop."
echo ""

# Loop: auto-restart on ffmpeg crash
while true; do
    ffmpeg \
        -loglevel warning \
        -f alsa -ac "$CHANNELS" -ar "$SAMPLE_RATE" -i "$ALSA_DEVICE" \
        -c:a libopus \
        -b:a 32k \
        -application lowdelay \
        -frame_duration 20 \
        -vbr off \
        -compression_level 5 \
        -f rtsp -rtsp_transport udp \
        "$MEDIAMTX_URL" \
    || true
    echo "[pi_streamer] ffmpeg exited, restarting in 3s …"
    sleep 3
done
