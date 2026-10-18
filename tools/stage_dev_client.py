#!/usr/bin/env python3
"""Stage uploaded named classes for Loom's dev client, without changing the release JAR.

Loom runClient loads build/classes/java/main, not the zipTrees bundled by jar.
ZIP files may include read-only directory permissions, so use zipfile rather
than extracting them with unzip. This task is for manual CI smoke tests only.
"""

from pathlib import Path
from zipfile import ZipFile

from prepare_archives import ROOT, prepare


def stage(output: Path) -> int:
    zelith, async_jar = prepare(ROOT / "build" / "prepared")
    output.mkdir(parents=True, exist_ok=True)
    root = output.resolve()
    count = 0
    for jar in (zelith, async_jar):
        with ZipFile(jar) as source:
            for name in source.namelist():
                if name.endswith("/") or name == "fabric.mod.json" or name.startswith("META-INF/"):
                    continue
                if jar == async_jar and (name.endswith("mixins.json") or
                     name.startswith("brightspark/asynclocator/asynclocatormodfabric/client/mixin/")):
                    continue
                destination = output / name
                if not destination.resolve().is_relative_to(root):
                    raise ValueError(f"Unsafe archive path: {name}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    raise ValueError(f"Uploaded JAR would overwrite an existing class/resource: {name}")
                destination.write_bytes(source.read(name))
                count += 1
    for original in (ROOT / "build" / "prepared" / "generated").glob("*.class"):
        destination = output / original.name
        if destination.exists():
            raise ValueError(f"Generated adapter would overwrite a class: {original.name}")
        destination.write_bytes(original.read_bytes())
        count += 1
    print(f"Staged {count} original resources/classes and generated adapters for dev run")
    return count


if __name__ == "__main__":
    stage(ROOT / "build" / "classes" / "java" / "main")
