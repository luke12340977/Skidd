#!/usr/bin/env python3
"""Expose client startup crashes via GitHub check annotations (no log ZIP needed)."""

import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
exit_code = int(sys.argv[2])
# Gradle sometimes prints a 20KB single-line classpath; GitHub truncates an
# annotation to 4KB and that line can hide the actual exception entirely.
raw_lines = text.splitlines()
lines = [line[:450] + (" ... [line truncated]" if len(line) > 450 else "")
         for line in raw_lines]
mod_lines = [line.strip() for line in raw_lines if re.search(r"^\s*- zelith\s+1\.0\.0\b", line)]
key_sent = "GUI_KEY_SENT" in text
notice = (f"release_mod_loaded={bool(mod_lines)}; gui_key_sent={key_sent}; "
          f"mod_entry={(mod_lines[0] if mod_lines else 'missing')[:300]}")
print("::notice title=Packaged mod smoke status::" + notice)
problems = re.compile(
    r"Exception in thread|Caused by:|MixinApplyError|MixinTransformerError|"
    r"ClassNotFoundException|NoClassDefFoundError|NoSuchMethodError|"
    r"VerifyError|Crash Report|FAILURE: Build failed|Failed to start the minecraft client",
    re.I,
)
# Missing optional flite narration and authlib connection timeouts are logged
# with stacktraces by Minecraft but do not, by themselves, stop the renderer.
def handled_background_error(index: int, line: str) -> bool:
    if "flite" in line.lower():
        return True
    nearby = "\n".join(raw_lines[index : index + 48]).lower()
    return ("sockettimeoutexception" in line.lower() and
            "com.mojang.authlib.minecraft.client.minecraftclient" in nearby)

failures = [i for i, line in enumerate(lines)
            if problems.search(line) and not handled_background_error(i, line)]
started = bool(re.search(r"Backend library: LWJGL|Reloading ResourceManager", text, re.I))
if failures or exit_code not in (0, 124) or not started or not mod_lines:
    if failures:
        # Keep the *first* exception; Gradle's later wrapper usually only
        # reports a generic non-zero subprocess exit.
        excerpt = "\n".join(lines[max(0, failures[0] - 3) : failures[0] + 22])
    else:
        excerpt = "\n".join(lines[-30:])
    crash_reports = sorted(Path("run/crash-reports").glob("*.txt"))
    if crash_reports:
        report = crash_reports[-1].read_text(encoding="utf-8", errors="replace")
        excerpt += "\nLATEST CRASH REPORT:\n" + "\n".join(report.splitlines()[:24])
    message = (f"Client exit={exit_code}; reached renderer={started}; "
               f"packaged Zelith loaded={bool(mod_lines)}; GUI key sent={key_sent}\n" + excerpt)
    encoded = message[:3500].replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print("::error title=Minecraft client startup crash::" + encoded)
    raise SystemExit(1)
if "GUI_KEY_SENT" in text:
    print("Minecraft 1.21.11 opened without a reported crash after the GUI key was sent "
          "(visual interaction not verified).")
else:
    print("Minecraft 1.21.11 opened without a reported startup crash "
          "(GUI key injection did not run; GUI interactions not verified).")
