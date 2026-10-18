#!/usr/bin/env python3
"""Expose client startup crashes via GitHub check annotations (no log ZIP needed)."""

import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
exit_code = int(sys.argv[2])
lines = text.splitlines()
problems = re.compile(
    r"Exception in thread|Caused by:|MixinApplyError|MixinTransformerError|"
    r"ClassNotFoundException|NoClassDefFoundError|NoSuchMethodError|"
    r"VerifyError|Crash Report|FAILURE: Build failed|Failed to start the minecraft client",
    re.I,
)
failures = [i for i, line in enumerate(lines) if problems.search(line)]
started = bool(re.search(r"Backend library: LWJGL|Reloading ResourceManager", text, re.I))
if failures or exit_code not in (0, 124) or not started:
    if failures:
        # Show the first underlying exception and its stack, plus the last
        # exception (Gradle's wrapper often only reports a non-zero exit).
        excerpts = [lines[max(0, i - 8) : min(len(lines), i + 55)] for i in (failures[0], failures[-1])]
        excerpt = "\n...\n".join("\n".join(group) for group in excerpts)
    else:
        excerpt = "\n".join(lines[-100:])
    message = f"Client exit={exit_code}; reached game renderer={started}\n" + excerpt
    encoded = message[-18000:].replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print("::error title=Minecraft client startup crash::" + encoded)
    raise SystemExit(1)
print("Minecraft 1.21.11 opened without a reported startup exception "
      "(timed out at title screen; GUI interactions not verified).")
