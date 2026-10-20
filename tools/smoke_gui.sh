#!/usr/bin/env bash
# Executed inside xvfb-run. Press Right Shift after the title window appears
# to exercise Zelith's original ClickGUI path, not just the Fabric entrypoint.
set -u
if [ "$#" -eq 0 ]; then
  echo 'Usage: smoke_gui.sh command [args...]' >&2
  exit 2
fi
(
  for attempt in $(seq 1 70); do
    sleep 2
    if grep -q 'Reloading ResourceManager' client-smoke.log; then
      window=$(xdotool search --name 'Minecraft' 2>/dev/null | head -n 1)
      if [ -n "$window" ]; then
        sleep 12
        xdotool windowfocus --sync "$window" 2>/dev/null || true
        if xdotool key --clearmodifiers Shift_R 2>/dev/null; then
          echo 'GUI_KEY_SENT Right Shift'
        else
          echo 'GUI_KEY_FAILED Right Shift'
        fi
        break
      fi
    fi
  done
) &
"$@"
