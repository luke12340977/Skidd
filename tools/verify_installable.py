#!/usr/bin/env python3
"""Check the final, remapped JAR rather than only its prepared build inputs.

This is a packaging/version verification, not a Minecraft runtime test.
"""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path

from prepare_archives import ROOT, constant_pool_strings

EXPECTED_CLASSES = (
    "com/zelith/ZelithClient.class",
    "com/zelith/gui/ClickGUI.class",
    "brightspark/asynclocator/asynclocatormodfabric/client/AsyncLocatorClient.class",
    "brightspark/asynclocator/asynclocatormodfabric/client/SilentRot.class",
    "b.class",  # Original locator algorithm, not a replacement implementation.
    "Module_AsyncLocator.class",
    "Module_InstaPearlCatch.class",
    "Module_STrigger.class",
    "Module_Aimbot.class",
    "com/zelith/integration/FastPearlCatch.class",
    "com/zelith/integration/STrigger.class",
    "com/zelith/integration/Aimbot.class",
    "com/zelith/integration/mixin/ClickGuiBindMixin.class",
)
EXPECTED_ENTRYPOINTS = (
    "com.zelith.ZelithClient",
    "brightspark.asynclocator.asynclocatormodfabric.client.AsyncLocatorClient",
    "com.zelith.integration.FastPearlCatch",
)
EXPECTED_MIXINS = (
    "zelith.mixins.json",
    "async-locator.client.mixins.json",
    "zelith-integration.mixins.json",
)


def verify(path: Path, *, game_version: str, mod_version: str) -> None:
    with zipfile.ZipFile(path) as jar:
        names = jar.namelist()
        contents = set(names)
        if len(names) != len(contents):
            raise ValueError("The installable JAR contains duplicate ZIP entries")
        missing = (set(EXPECTED_CLASSES) | set(EXPECTED_MIXINS)
                   | {"fabric.mod.json", "zelith-refmap.json",
                      "assets/zelith/shaders/arc_fragment.fsh"}) - contents
        if missing:
            raise ValueError(f"The installable JAR is missing required features: {sorted(missing)}")

        metadata = json.loads(jar.read("fabric.mod.json"))
        if metadata.get("id") != "zelith":
            raise ValueError("The installable JAR does not have Zelith's mod ID")
        if metadata.get("version") != mod_version:
            raise ValueError(f"Wrong mod version in installable JAR: {metadata.get('version')}")
        if metadata.get("depends", {}).get("minecraft") != "~" + game_version:
            raise ValueError(f"Wrong Minecraft dependency in installable JAR: {metadata.get('depends')}")
        if tuple(metadata.get("entrypoints", {}).get("client", ())) != EXPECTED_ENTRYPOINTS:
            raise ValueError("The combined JAR does not initialize all three client entrypoints")
        if tuple(metadata.get("mixins", ())) != EXPECTED_MIXINS:
            raise ValueError("The combined JAR is not loading all three mixin configurations")
        for entry in EXPECTED_ENTRYPOINTS:
            if entry.replace(".", "/") + ".class" not in contents:
                raise ValueError(f"Client entrypoint {entry} has no class file")

        # A distributable Fabric JAR must use intermediary Minecraft names.
        # The original ZIPs contain named/Yarn references, so a JAR that only
        # merged the inputs without remapJar would fail on a normal client.
        pool = {text for _, text in constant_pool_strings(jar.read("b.class"))}
        if b"net/minecraft/class_310" not in pool:
            raise ValueError("The original Async Locator was not remapped to intermediary")
        if b"net/minecraft/client/MinecraftClient" in pool:
            raise ValueError("Named Minecraft class leaked into the remapped locator binary")
    print(f"Verified {path}: Minecraft {game_version}, {len(contents)} ZIP entries,"
          " original GUI and Async tracking, four Combat modules and all mixins")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jar", type=Path)
    args = parser.parse_args()
    properties = (ROOT / "gradle.properties").read_text()
    game_version = re.search(r"^minecraft_version=(.+)$", properties, re.MULTILINE).group(1)
    mod_version = re.search(r"^mod_version=(.+)$", properties, re.MULTILINE).group(1)
    verify(args.jar, game_version=game_version, mod_version=mod_version)


if __name__ == "__main__":
    main()
