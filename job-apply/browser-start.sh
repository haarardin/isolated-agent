#!/usr/bin/env bash
set -euo pipefail
[[ "$BROWSER_MODE" == headless || "$BROWSER_MODE" == headed ]] || { echo "Invalid BROWSER_MODE" >&2; exit 2; }
args=(--browser chromium --executable-path /usr/bin/chromium --no-sandbox
      --user-data-dir /browser-profile --output-dir /workspace/captures
      --host 0.0.0.0 --port 8931 --shared-browser-context
      --caps devtools)
if [[ "$BROWSER_MODE" == headed ]]; then
  Xvfb :99 -screen 0 1440x900x24 -nolisten tcp >/tmp/xvfb.log 2>&1 &
  for i in {1..30}; do
    [[ -e /tmp/.X11-unix/X99 ]] && break
    sleep 0.2
  done
  [[ -e /tmp/.X11-unix/X99 ]] || { cat /tmp/xvfb.log; exit 1; }
  x11vnc -display :99 -rfbauth /secrets/passwd -rfbport 5900 \
    -listen 0.0.0.0 -forever -shared -bg -o /tmp/x11vnc.log
  websockify --web /usr/share/novnc 0.0.0.0:6080 127.0.0.1:5900 >/tmp/novnc.log 2>&1 &
else
  args+=(--headless)
fi
exec playwright-mcp "${args[@]}"
