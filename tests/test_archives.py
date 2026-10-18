"""No Fabric download or Java installation required: inspect the build inputs."""

import hashlib
import json
import re
import struct
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from prepare_archives import CLASS_ALIASES, ZELITH_ZIP, constant_pool_strings, prepare


# Minimal class-file reader for validating the decompiler's repaired API. A
# missing type in a descriptor fails at JVM class loading, not only at compile.
def members(data):
    cp = {}
    offset = 10
    count = struct.unpack_from(">H", data, 8)[0]
    i = 1
    while i < count:
        tag = data[offset]
        if tag == 1:
            length = struct.unpack_from(">H", data, offset + 1)[0]
            # Java uses modified UTF-8; member names/descriptors are ASCII, but
            # unrelated string constants may contain surrogate byte sequences.
            cp[i] = data[offset + 3 : offset + 3 + length].decode("utf-8", "replace")
            offset += 3 + length
        elif tag in (3, 4, 9, 10, 11, 12, 17, 18):
            offset += 5
        elif tag in (5, 6):
            offset += 9
            i += 1
        elif tag in (7, 8, 16, 19, 20):
            offset += 3
        elif tag == 15:
            offset += 4
        else:
            raise AssertionError(f"Unexpected constant-pool tag {tag}")
        i += 1

    # access_flags, this_class, super_class, interfaces_count
    interfaces = struct.unpack_from(">H", data, offset + 6)[0]
    offset += 8 + 2 * interfaces
    groups = []
    for _ in range(2):  # fields, methods
        size = struct.unpack_from(">H", data, offset)[0]
        offset += 2
        group = []
        for _ in range(size):
            _, name, descriptor, attr_count = struct.unpack_from(">HHHH", data, offset)
            group.append((cp[name], cp[descriptor]))
            offset += 8
            for _ in range(attr_count):
                length = struct.unpack_from(">I", data, offset + 2)[0]
                offset += 6 + length
        groups.append(group)
    return groups


class ArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.zelith_path, cls.async_path = prepare(ROOT / "build" / "prepared")

    def test_original_aliases_are_repaired(self):
        with zipfile.ZipFile(ZELITH_ZIP) as outer:
            import io
            with zipfile.ZipFile(io.BytesIO(outer.read("Zelith-renamed-remapped.jar"))) as original:
                fields, methods = members(original.read("Module.class"))
                self.assertIn(("<init>", "(Ljava/lang/String;Lg;)V"), methods)
        with zipfile.ZipFile(self.zelith_path) as repaired:
            fields, methods = members(repaired.read("Module.class"))
            self.assertIn(("<init>", "(Ljava/lang/String;LCategory;)V"), methods)
            self.assertIn(("c", "(I)V"), methods)
            self.assertIn(("HwidGen", "()Z"), methods)
            self.assertIn(("Category", "()V"), methods)
            self.assertIn(("LicenseState", "()V"), methods)
            fields, methods = members(repaired.read("Module_f.class"))
            self.assertIn(("<init>", "(Ljava/lang/String;LCategory;)V"), methods)
            self.assertIn(("KeyFile", "()V"), methods)
            fields, methods = members(repaired.read("Category.class"))
            self.assertIn(("c", "LCategory;"), fields)  # Combat

    def test_all_local_descriptor_types_exist_and_no_duplicate_members(self):
        # Ignore paths in third-party types, e.g. MethodHandles$Lookup.
        unqualified = re.compile(rb"(?<![\w/$])L([a-z][a-z0-9_$]*);")
        with zipfile.ZipFile(self.zelith_path) as z:
            classes = {n[:-6] for n in z.namelist() if n.endswith(".class")}
            self.assertEqual(len(classes), 167)
            self.assertTrue(set(CLASS_ALIASES.values()).issubset(classes))
            for owner in classes:
                data = z.read(owner + ".class")
                fields, methods = members(data)
                self.assertEqual(len(fields), len(set(fields)), owner + " fields")
                self.assertEqual(len(methods), len(set(methods)), owner + " methods")
                for _, value in constant_pool_strings(data):
                    for match in unqualified.finditer(value):
                        self.assertIn(match.group(1).decode(), classes, owner)

    def test_generated_combat_module_matches_zelith_api(self):
        data = (ROOT / "build" / "prepared" / "generated" / "Module_AsyncLocator.class").read_bytes()
        self.assertEqual(struct.unpack_from(">H", data, 6)[0], 65)  # Java 21
        fields, methods = members(data)
        self.assertEqual(fields, [("middleMouse", "LSetting;"), ("requireSneak", "LSetting;")])
        self.assertEqual(methods, [("<init>", "()V"), ("middleMouseEnabled", "()Z"),
                                   ("requiresSneak", "()Z"), ("Module_f", "()V")])
        constants = {raw.decode("ascii") for _, raw in constant_pool_strings(data)}
        for value in ("Async Locator", "Middle Mouse Trigger", "Require Sneak", "Category",
                      "Module_f", "com/zelith/integration/AsyncLocatorGate", "(LSetting;)V"):
            self.assertIn(value, constants)

    def test_generated_insta_pearl_catch_module(self):
        data = (ROOT / "build" / "prepared" / "generated" / "Module_InstaPearlCatch.class").read_bytes()
        self.assertEqual(struct.unpack_from(">H", data, 6)[0], 65)
        fields, methods = members(data)
        self.assertEqual(fields, [("delayTicks", "LSetting;"), ("restoreSlot", "LSetting;")])
        self.assertEqual(methods, [("<init>", "()V"), ("delayValue", "()Ljava/lang/Object;"),
                                   ("restoreSlotEnabled", "()Z"), ("Module_f", "()V")])
        constants = {raw.decode("ascii", "replace") for _, raw in constant_pool_strings(data)}
        for value in ("Insta Pearl Catch", "Delay Ticks", "Restore Slot", "Category",
                      "Module_f", "com/zelith/integration/FastPearlCatch", "(LSetting;)V"):
            self.assertIn(value, constants)
        self.assertIn(b"\x42\x20\x00\x00", data)  # 40.0F maximum delay
        registration = (ROOT / "src/main/java/com/zelith/integration/mixin/RegistryMixin.java").read_text()
        activation = (ROOT / "src/main/java/com/zelith/integration/mixin/ActivationBindMixin.java").read_text()
        self.assertIn('"Module_InstaPearlCatch"', registration)
        self.assertIn('"Module_InstaPearlCatch"', activation)
        self.assertIn("FastPearlCatch.trigger()", activation)

    def test_generated_s_trigger_module(self):
        data = (ROOT / "build" / "prepared" / "generated" / "Module_STrigger.class").read_bytes()
        self.assertEqual(struct.unpack_from(">H", data, 6)[0], 65)
        fields, methods = members(data)
        self.assertEqual(fields, [("hitDelay", "LSetting;"), ("aimFov", "LSetting;"),
                                  ("playersOnly", "LSetting;")])
        self.assertEqual(methods, [("<init>", "()V"), ("hitDelayValue", "()Ljava/lang/Object;"),
                                   ("aimFovValue", "()Ljava/lang/Object;"),
                                   ("playersOnlyEnabled", "()Z"), ("LicenseState", "()V"),
                                   ("Module_f", "()V"), ("Category", "()V")])
        constants = {raw.decode("ascii", "replace") for _, raw in constant_pool_strings(data)}
        for value in ("S Trigger", "Hit Delay Ticks", "Aim FOV", "Players Only", "Category",
                      "Module", "com/zelith/integration/STrigger", "(LSetting;)V"):
            self.assertIn(value, constants)
        for number in (10.0, 12.0, 40.0, 45.0):
            self.assertIn(struct.pack(">f", number), data)
        registration = (ROOT / "src/main/java/com/zelith/integration/mixin/RegistryMixin.java").read_text()
        self.assertIn('"Module_STrigger"', registration)
        with zipfile.ZipFile(self.zelith_path) as zelith:
            friend_methods = members(zelith.read("Module_Friends.class"))[1]
            self.assertIn(("KeyFile", "()Z"), friend_methods)
            self.assertIn(("HwidGen", "(Ljava/lang/String;)Z"), friend_methods)

    def test_generated_aimbot_module(self):
        data = (ROOT / "build" / "prepared" / "generated" / "Module_Aimbot.class").read_bytes()
        self.assertEqual(struct.unpack_from(">H", data, 6)[0], 65)
        fields, methods = members(data)
        self.assertEqual(fields, [(name, "LSetting;") for name in (
            "aimFov", "turnSpeed", "leadTicks", "range", "projectileSpeed",
            "playersOnly", "aimHead", "holdAttack")])
        self.assertEqual(methods, [("<init>", "()V"),
            *[(name, "()Ljava/lang/Object;") for name in (
                "aimFovValue", "turnSpeedValue", "leadTicksValue", "rangeValue", "projectileSpeedValue")],
            *[(name, "()Z") for name in ("playersOnlyEnabled", "aimHeadEnabled", "holdAttackEnabled")],
            ("LicenseState", "()V"), ("Module_f", "()V"), ("Category", "()V")])
        constants = {raw.decode("ascii", "replace") for _, raw in constant_pool_strings(data)}
        for value in ("Aimbot", "Aim FOV", "Turn Deg/Tick", "Lead Ticks", "Range Blocks",
                      "Projectile Speed", "Players Only", "Aim Head", "Hold Attack",
                      "Category", "Module", "com/zelith/integration/Aimbot"):
            self.assertIn(value, constants)
        for number in (15.0, 16.0, 20.0, 32.0, 45.0):
            self.assertIn(struct.pack(">f", number), data)
        registration = (ROOT / "src/main/java/com/zelith/integration/mixin/RegistryMixin.java").read_text()
        self.assertIn('"Module_Aimbot"', registration)
        service = (ROOT / "src/main/java/com/zelith/integration/Aimbot.java").read_text()
        self.assertIn("turnToward(", service)
        self.assertNotIn("attackEntity(", service)
        self.assertNotIn("sendPacket(", service)

    def test_jar_contains_exact_original_algorithms_and_assets(self):
        with zipfile.ZipFile(self.zelith_path) as zelith:
            self.assertIn("zelith.mixins.json", zelith.namelist())
            self.assertIn("zelith-refmap.json", zelith.namelist())
            self.assertIn("assets/zelith/shaders/arc_fragment.fsh", zelith.namelist())
        with zipfile.ZipFile(self.async_path) as async_:
            self.assertIn("b.class", async_.namelist())
            self.assertIn("brightspark/asynclocator/asynclocatormodfabric/client/AsyncLocatorClient.class", async_.namelist())
            self.assertIn(("held", "()Z"), members(async_.read(
                "brightspark/asynclocator/asynclocatormodfabric/client/AsyncLocatorClient.class"))[1])
            self.assertIn(("b", "()V"), members(async_.read("b.class"))[1])
            self.assertIn(("c", "()V"), members(async_.read("b.class"))[1])

    def test_combined_jar_has_no_overlapping_files(self):
        with zipfile.ZipFile(self.zelith_path) as zelith, zipfile.ZipFile(self.async_path) as async_:
            first = {n for n in zelith.namelist() if not n.endswith("/")
                     and n != "fabric.mod.json" and not n.startswith("META-INF/")}
            second = {n for n in async_.namelist() if not n.endswith("/")
                      and n not in ("fabric.mod.json", "async-locator.mixins.json",
                                    "async-locator.client.mixins.json")
                      and not n.startswith("META-INF/")
                      and not n.startswith(
                          "brightspark/asynclocator/asynclocatormodfabric/client/mixin/")}
            self.assertFalse(first & second, sorted(first & second))
            generated = {"Module_AsyncLocator.class", "Module_InstaPearlCatch.class",
                         "Module_STrigger.class", "Module_Aimbot.class"}
            self.assertFalse(generated & (first | second), sorted(generated & (first | second)))

    def test_mixin_targets_match_binary_methods(self):
        targets = {
            "SwapHelper.class": [("Module", "()V"), ("Module_ActiveModules", "()V")],
            "Module_f.class": [("KeyFile", "()V")],
            "com/zelith/gui/ClickGUI.class": [
                ("keyPressed", "(Lnet/minecraft/client/input/KeyInput;)Z"),
                ("pollBindKeys", "()V"),
                ("getKeyDisplayNameStatic", "(I)Ljava/lang/String;"),
            ],
        }
        with zipfile.ZipFile(self.zelith_path) as z:
            for path, methods in targets.items():
                declared = members(z.read(path))[1]
                for method in methods:
                    self.assertIn(method, declared, path)
        with zipfile.ZipFile(self.async_path) as z:
            declared = members(z.read(
                "brightspark/asynclocator/asynclocatormodfabric/client/AsyncLocatorClient.class"))[1]
            self.assertIn(("onClientTick", "()V"), declared)

    def test_resource_registration_is_consistent(self):
        resources = ROOT / "src" / "main" / "resources"
        mod = json.loads((resources / "fabric.mod.json").read_text())
        properties = (ROOT / "gradle.properties").read_text()
        game_version = re.search(r"^minecraft_version=(.+)$", properties, re.MULTILINE).group(1)
        self.assertEqual(game_version, "1.21.11")
        self.assertEqual(mod["depends"]["minecraft"], "~" + game_version)
        fabric_api = re.search(r"^fabric_api_version=(.+)$", properties, re.MULTILINE).group(1)
        self.assertTrue(fabric_api.endswith("+" + game_version), fabric_api)
        self.assertEqual(mod["id"], "zelith")
        self.assertEqual(len(mod["entrypoints"]["client"]), 3)
        self.assertIn("com.zelith.integration.FastPearlCatch", mod["entrypoints"]["client"])
        self.assertEqual(len(mod["mixins"]), 3)
        for name in mod["mixins"]:
            if (resources / name).exists():
                config = json.loads((resources / name).read_text())
                for mixin in config["client"]:
                    source = ROOT / "src" / "main" / "java" / Path(*config["package"].split(".")) / (mixin + ".java")
                    self.assertTrue(source.is_file(), f"Missing mixin source: {source}")

    def test_uploaded_mods_share_1_21_11_mappings_and_metadata(self):
        archives = (ZELITH_ZIP, ROOT / "async-locator-1.0.3-fabric-loader-0.18-decompiled.zip")
        mappings = []
        for archive in archives:
            with zipfile.ZipFile(archive) as z:
                original_mod = json.loads(z.read("sources/fabric.mod.json"))
                self.assertEqual(original_mod["depends"]["minecraft"], "~1.21.11", archive.name)
                self.assertEqual(original_mod["depends"]["java"], ">=21", archive.name)
                mappings.append(hashlib.sha256(z.read("mappings-used.tiny")).digest())
        self.assertEqual(mappings[0], mappings[1], "Uploaded mods must use the same mappings")

    def test_preparation_is_reproducible(self):
        generated = ROOT / "build" / "prepared" / "generated"
        paths = [self.zelith_path, generated / "Module_AsyncLocator.class",
                 generated / "Module_InstaPearlCatch.class", generated / "Module_STrigger.class",
                 generated / "Module_Aimbot.class"]
        before = [hashlib.sha256(path.read_bytes()).digest() for path in paths]
        prepare(ROOT / "build" / "prepared")
        after = [hashlib.sha256(path.read_bytes()).digest() for path in paths]
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
