#!/usr/bin/env bash
# One command: checks ffmpeg, sets up Python, starts the website.
set -e
cd "$(dirname "$0")"
if ! command -v ffmpeg >/dev/null; then
  echo "ffmpeg is missing."
  echo "  Termux : pkg install ffmpeg python"
  echo "  Ubuntu : sudo apt install ffmpeg python3 python3-venv"
  exit 1
fi
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
python app.py "$@"
