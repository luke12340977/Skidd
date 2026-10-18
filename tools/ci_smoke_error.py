#!/usr/bin/env python3
"""Expose client startup crashes via GitHub check annotations (no log ZIP needed)."""

import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
exit_code = int(sys.argv[2])
# Gradle sometimes prints a 20KB single-line classpath; GitHub truncates an
# annotation to 4KB and that line can hide the actual exception entirely.
lines = [line[:450] + (" ... [line truncated]" if len(line) > 450 else "")
         for line in text.splitlines()]
problems = re.compile(
    r"Exception in thread|Caused by:|MixinApplyError|MixinTransformerError|"
    r"ClassNotFoundException|NoClassDefFoundError|NoSuchMethodError|"
    r"VerifyError|Crash Report|FAILURE: Build failed|Failed to start the minecraft client",
    re.I,
)
# A missing optional Linux narrator library (flite) logs a handled stacktrace
# on headless CI, but is not a mod crash and does not prevent the menu loading.
failures = [i for i, line in enumerate(lines)
            if problems.search(line) and "flite" not in line.lower()]
started = bool(re.search(r"Backend library: LWJGL|Reloading ResourceManager", text, re.I))
if failures or exit_code not in (0, 124) or not started:
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
    message = f"Client exit={exit_code}; reached game renderer={started}\n" + excerpt
    encoded = message[:3500].replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print("::error title=Minecraft client startup crash::" + encoded)
    raise SystemExit(1)
if "GUI_KEY_SENT" in text:
    print("Minecraft 1.21.11 opened without a reported crash after the GUI key was sent "
          "(visual interaction not verified).")
else:
    print("Minecraft 1.21.11 opened without a reported startup crash "
          "(GUI key injection did not run; GUI interactions not verified).")
