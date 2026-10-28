#!/usr/bin/env sh
# LaunchPad starter for macOS and Linux
cd "$(dirname "$0")" || exit 1
PY=python3
command -v "$PY" >/dev/null 2>&1 || PY=python
command -v "$PY" >/dev/null 2>&1 || { echo "Python 3 was not found. Install it from https://www.python.org/downloads/"; exit 1; }
# Optional extra: phone QR codes. LaunchPad works fine without it.
"$PY" -c "import qrcode" >/dev/null 2>&1 || "$PY" -m pip install --quiet --user qrcode pillow >/dev/null 2>&1
exec "$PY" launchpad.py "$@"
