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
BITRATE="${BITRATE:-64k}"       # Opus 码率，可通过环境变量覆盖：BITRATE=96k bash agent/pi_streamer.sh

echo "[pi_streamer] Input:  ALSA device='$ALSA_DEVICE' ${SAMPLE_RATE}Hz stereo→mono(c0)"
echo "[pi_streamer] Codec:  libopus ${BITRATE} VBR lowdelay frame=20ms"
echo "[pi_streamer] Output: $MEDIAMTX_URL  (UDP)"
echo "[pi_streamer] Press Ctrl+C to stop."
echo ""

# Loop: auto-restart on ffmpeg crash
while true; do
    # ALSA 拿原始 stereo（ReSpeaker UAC1.0 firmware 是 2ch 输出）→ pan filter
    # 显式取 channel 0，避免 ffmpeg 自动 L+R 平均把另一道的噪声也带进来。
    # VBR (constrained) + 64k 是 voice/婴儿监控的甜点：嘶嘶底噪几乎消失，
    # 仍远低于 AAC 128k stereo 的码率。
    ffmpeg \
        -loglevel warning \
        -f alsa -ac 2 -ar "$SAMPLE_RATE" -i "$ALSA_DEVICE" \
        -af "pan=mono|c0=c0" \
        -c:a libopus \
        -b:a "$BITRATE" \
        -vbr constrained \
        -application lowdelay \
        -frame_duration 20 \
        -compression_level 5 \
        -f rtsp -rtsp_transport udp \
        "$MEDIAMTX_URL" \
    || true
    echo "[pi_streamer] ffmpeg exited, restarting in 3s …"
    sleep 3
done
