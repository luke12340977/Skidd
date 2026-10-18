"""Exercise the final-JAR packaging check without a Gradle installation."""

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from generate_module import Pool, u2
from verify_installable import EXPECTED_CLASSES, EXPECTED_ENTRYPOINTS, EXPECTED_MIXINS, verify


def fixture_class() -> bytes:
    pool = Pool()
    this = pool.clazz("b")
    parent = pool.clazz("java/lang/Object")
    pool.clazz("net/minecraft/class_310")
    return (b"\xca\xfe\xba\xbe" + u2(0) + u2(65) + u2(len(pool.entries) + 1)
            + b"".join(pool.entries) + u2(0x21) + u2(this) + u2(parent)
            + u2(0) + u2(0) + u2(0) + u2(0))


class InstallableVerifierTests(unittest.TestCase):
    def make_jar(self, path, *, version="~1.21.11", include_aimbot=True):
        metadata = {
            "id": "zelith", "version": "1.0.0", "depends": {"minecraft": version},
            "entrypoints": {"client": EXPECTED_ENTRYPOINTS}, "mixins": EXPECTED_MIXINS,
        }
        with zipfile.ZipFile(path, "w") as jar:
            jar.writestr("fabric.mod.json", json.dumps(metadata))
            jar.writestr("zelith-refmap.json", "{}")
            jar.writestr("assets/zelith/shaders/arc_fragment.fsh", "")
            for name in EXPECTED_MIXINS:
                jar.writestr(name, "{}")
            for name in EXPECTED_CLASSES:
                if name != "Module_Aimbot.class" or include_aimbot:
                    jar.writestr(name, fixture_class() if name == "b.class" else b"example")

    def test_complete_integrated_jar_is_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "integrated.jar"
            self.make_jar(path)
            verify(path, game_version="1.21.11", mod_version="1.0.0")

    def test_wrong_minecraft_version_or_missing_combat_module_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "integrated.jar"
            self.make_jar(path, version="~1.21.4")
            with self.assertRaisesRegex(ValueError, "Minecraft dependency"):
                verify(path, game_version="1.21.11", mod_version="1.0.0")
            self.make_jar(path, include_aimbot=False)
            with self.assertRaisesRegex(ValueError, "Module_Aimbot.class"):
                verify(path, game_version="1.21.11", mod_version="1.0.0")


if __name__ == "__main__":
    unittest.main()
