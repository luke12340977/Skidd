"""Check the porting audit without downloading another Minecraft version."""

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from audit_minecraft_api import audit, constant_pool, references, source_mappings, target_mappings
from generate_module import Pool, u2


class ApiAuditTests(unittest.TestCase):
    OLD = "\n".join([
        "tiny\t2\t0\tintermediary\tnamed",
        "c\tnet/minecraft/class_332\tnet/minecraft/client/gui/DrawContext",
        "\tm\t()Lorg/joml/Matrix3x2fStack;\tmethod_51448\tgetMatrices",
        "\tm\t()I\tmethod_00000\toldMethod",
        "c\tnet/minecraft/class_11908\tnet/minecraft/client/input/KeyInput",
        "c\tnet/minecraft/class_310\tnet/minecraft/client/MinecraftClient",
        "\tf\tLnet/minecraft/class_11908;\tfield_00000\tkeyInput",
    ])
    NEW = "\n".join([
        "v1\tofficial\tintermediary",
        "CLASS\ta\tnet/minecraft/class_332",
        "CLASS\tb\tnet/minecraft/class_310",
        "METHOD\ta\t()Lnet/minecraft/class_310;\ta\tmethod_00000",
        "METHOD\ta\t()Lnet/minecraft/class_310;\tb\tmethod_51448",
    ])

    @staticmethod
    def fixture_class():
        pool = Pool()
        this = pool.clazz("Example")
        parent = pool.clazz("java/lang/Object")
        pool.clazz("net/minecraft/client/input/KeyInput")
        pool.method("net/minecraft/client/gui/DrawContext", "getMatrices",
                    "()Lorg/joml/Matrix3x2fStack;")
        pool.method("net/minecraft/client/gui/DrawContext", "oldMethod", "()I")
        # Present only inside a descriptor, not as its own CONSTANT_Class.
        pool.field("net/minecraft/client/MinecraftClient", "keyInput",
                   "Lnet/minecraft/client/input/KeyInput;")
        return (b"\xca\xfe\xba\xbe" + u2(0) + u2(65) + u2(len(pool.entries) + 1)
                + b"".join(pool.entries) + u2(0x21) + u2(this) + u2(parent)
                + u2(0) + u2(0) + u2(0) + u2(0))

    def test_mapping_formats_and_descriptor_translation(self):
        classes, members = source_mappings(self.OLD)
        self.assertEqual(classes["net/minecraft/class_11908"], "net/minecraft/client/input/KeyInput")
        self.assertIn(("net/minecraft/client/MinecraftClient", "field", "keyInput",
                       "Lnet/minecraft/client/input/KeyInput;"), members)
        classes, members, descriptors = target_mappings(self.NEW)
        self.assertNotIn("net/minecraft/class_11908", classes)
        self.assertEqual(descriptors[("net/minecraft/class_332", "method", "method_51448")],
                         {"()Lnet/minecraft/class_310;"})
        with self.assertRaises(ValueError):
            target_mappings("tiny\t2\t0\tintermediary\tnamed")

    def test_constant_pool_and_refs(self):
        data = self.fixture_class()
        self.assertTrue(constant_pool(data))
        class_refs, member_refs = references(data)
        self.assertIn("net/minecraft/client/input/KeyInput", class_refs)
        self.assertIn(("net/minecraft/client/gui/DrawContext", "method", "getMatrices",
                       "()Lorg/joml/Matrix3x2fStack;"), member_refs)
        self.assertIn(("net/minecraft/client/MinecraftClient", "field", "keyInput",
                       "Lnet/minecraft/client/input/KeyInput;"), member_refs)
        with self.assertRaises(ValueError):
            constant_pool(b"not a class")

    def test_audit_catches_missing_class_and_changed_method(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "original.jar"
            with zipfile.ZipFile(path, "w") as jar:
                jar.writestr("Example.class", self.fixture_class())
            count, matches, absent, changed, unknown = audit([path], self.OLD, self.NEW)
        self.assertEqual(count, 1)
        self.assertEqual(matches, 0)
        self.assertIn(("net/minecraft/client/input/KeyInput", "net/minecraft/class_11908"), absent)
        self.assertEqual(len(changed), 3)
        self.assertEqual(len(unknown), 0)
        self.assertIn(("net/minecraft/client/gui/DrawContext", "method", "getMatrices",
                       "()Lorg/joml/Matrix3x2fStack;"), [key[0] for key in changed])


if __name__ == "__main__":
    unittest.main()
