#!/usr/bin/env bash
# Frames + narration + music -> lapi-tour.mp4 (H.264/AAC), plus a WebVTT caption file.
# Runs ffmpeg in a container; the video folder is mounted at /v.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
WIN_DIR="$(cygpath -w "$DIR" | sed 's#\\#/#g')"
docker run --rm -v "${WIN_DIR}:/v" -w /v jrottenberg/ffmpeg:6.1-ubuntu -y \
  -framerate 30 -i frames/f%05d.jpg -i voice.mp3 -i music.wav \
  -filter_complex "[2:a]volume=0.16,afade=t=out:st=63:d=4[m];[1:a]volume=1.0,adelay=150|150[v];[v][m]amix=inputs=2:duration=longest:dropout_transition=3,aresample=48000[a]" \
  -map 0:v -map "[a]" -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p -movflags +faststart -c:a aac -b:a 160k -shortest lapi-tour.mp4
ls -la "$DIR/lapi-tour.mp4"
