#!/usr/bin/env bash
# Pi Audio Streamer — publishes ReSpeaker audio as RTSP via mediamtx.
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
#   bash voice/agent/pi_streamer.sh
#   bash voice/agent/pi_streamer.sh hw:2,0    # override ALSA device

set -euo pipefail

ALSA_DEVICE="${1:-default}"     # PipeWire/PulseAudio default, or plughw:1,0 etc.
MEDIAMTX_URL="rtsp://localhost:8554/respeaker"
SAMPLE_RATE=48000               # 48 kHz — better quality for live monitoring
CHANNELS=2                      # stereo from ReSpeaker v2

echo "[pi_streamer] Input: ALSA device='$ALSA_DEVICE'"
echo "[pi_streamer] Output: $MEDIAMTX_URL"
echo "[pi_streamer] Press Ctrl+C to stop."
echo ""

# Loop: auto-restart on ffmpeg crash
while true; do
    ffmpeg \
        -loglevel warning \
        -f alsa -ac "$CHANNELS" -ar "$SAMPLE_RATE" -i "$ALSA_DEVICE" \
        -c:a aac -b:a 128k \
        -f rtsp -rtsp_transport tcp \
        "$MEDIAMTX_URL" \
    || true
    echo "[pi_streamer] ffmpeg exited, restarting in 3s …"
    sleep 3
done
