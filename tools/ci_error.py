#!/usr/bin/env python3
"""Surface a Gradle failure through GitHub's annotations API.

CI log ZIP downloads are not accessible from every development sandbox, while
check-run annotations are. Show compiler diagnostics immediately before the
Gradle failure as well as Gradle's own summary.
"""

from pathlib import Path
import sys


lines = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace").splitlines()
failures = [index for index, line in enumerate(lines) if "FAILURE: Build failed" in line]
if failures:
    index = failures[-1]
    excerpt = lines[max(0, index - 70) : index + 38]
else:
    excerpt = lines[-100:]
message = "\n".join(excerpt)[-10000:]
message = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
print("::error title=Gradle build failure::" + message)
