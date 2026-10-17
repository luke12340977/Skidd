"""Emit Combat modules against Zelith's bytecode-only API.

Zelith contains public methods that differ *only* by return type (for example,
Module.HwidGen() returns boolean, Category and List). JVM descriptors can
represent that, but Java source/javac cannot reliably subclass the decompiler's
renamed classes. This emitter avoids recompiling Zelith or depending on a
third-party bytecode package. It emits only straight-line methods: no branches
or StackMapTable frames are needed. The original Async Locator algorithm stays
in its uploaded binary; the new Combat behaviors live in readable Java.
"""

from __future__ import annotations

import struct
from pathlib import Path


def u2(value: int) -> bytes:
    return struct.pack(">H", value)


def u4(value: int) -> bytes:
    return struct.pack(">I", value)


class Pool:
    def __init__(self):
        self.entries: list[bytes] = []
        self.indices: dict[tuple, int] = {}

    def add(self, key: tuple, data: bytes) -> int:
        if key not in self.indices:
            self.indices[key] = len(self.entries) + 1
            self.entries.append(data)
        return self.indices[key]

    def utf8(self, text: str) -> int:
        data = text.encode("ascii")
        return self.add(("utf8", text), b"\x01" + u2(len(data)) + data)

    def clazz(self, name: str) -> int:
        return self.add(("class", name), b"\x07" + u2(self.utf8(name)))

    def string(self, text: str) -> int:
        return self.add(("string", text), b"\x08" + u2(self.utf8(text)))

    def float(self, value: float) -> int:
        return self.add(("float", value), b"\x04" + struct.pack(">f", value))

    def name_type(self, name: str, descriptor: str) -> int:
        return self.add(("name_type", name, descriptor),
                        b"\x0c" + u2(self.utf8(name)) + u2(self.utf8(descriptor)))

    def field(self, owner: str, name: str, descriptor: str) -> int:
        return self.add(("field", owner, name, descriptor),
                        b"\x09" + u2(self.clazz(owner)) + u2(self.name_type(name, descriptor)))

    def method(self, owner: str, name: str, descriptor: str) -> int:
        return self.add(("method", owner, name, descriptor),
                        b"\x0a" + u2(self.clazz(owner)) + u2(self.name_type(name, descriptor)))


def instruction(opcode: int, constant: int) -> bytes:
    return bytes([opcode]) + u2(constant)


def ldc(constant: int) -> bytes:
    if constant > 255:
        return b"\x13" + u2(constant)  # ldc_w
    return b"\x12" + bytes([constant])


def member(pool: Pool, name: str, descriptor: str, *, access: int, code: bytes | None = None,
           max_stack: int = 0) -> bytes:
    attributes = b""
    count = 0
    if code is not None:
        # Code: max_stack, max_locals (all instance methods), instructions,
        # empty exception table, empty code attributes.
        body = u2(max_stack) + u2(1) + u4(len(code)) + code + u2(0) + u2(0)
        attributes = u2(pool.utf8("Code")) + u4(len(body)) + body
        count = 1
    return (u2(access) + u2(pool.utf8(name)) + u2(pool.utf8(descriptor))
            + u2(count) + attributes)


def make_module_class() -> bytes:
    pool = Pool()
    this = pool.clazz("Module_AsyncLocator")
    parent = pool.clazz("Module_f")
    # 0xb2 getstatic, 0xb4 getfield, 0xb5 putfield, 0xb6 invokevirtual,
    # 0xb7 invokespecial, 0xb8 invokestatic, 0xbb new.
    category = instruction(0xb2, pool.field("Category", "c", "LCategory;"))
    super_ctor = instruction(0xb7, pool.method("Module_f", "<init>", "(Ljava/lang/String;LCategory;)V"))
    setting_ctor = instruction(0xb7, pool.method("Setting", "<init>", "(Ljava/lang/String;Ljava/lang/Object;)V"))
    boxed_bool = instruction(0xb8, pool.method("java/lang/Boolean", "valueOf", "(Z)Ljava/lang/Boolean;"))
    add_setting = instruction(0xb6, pool.method("Module", "HwidGen", "(LSetting;)V"))
    register = instruction(0xb8, pool.method("com/zelith/integration/AsyncLocatorGate", "register", "(Ljava/lang/Object;)V"))
    stop = instruction(0xb8, pool.method("com/zelith/integration/AsyncLocatorGate", "onDisabled", "()V"))
    setting_value = instruction(0xb6, pool.method("Setting", "HwidGen", "()Ljava/lang/Object;"))
    true_value = instruction(0xb2, pool.field("java/lang/Boolean", "TRUE", "Ljava/lang/Boolean;"))
    equals = instruction(0xb6, pool.method("java/lang/Boolean", "equals", "(Ljava/lang/Object;)Z"))

    fields = []
    for name in ("middleMouse", "requireSneak"):
        fields.append(member(pool, name, "LSetting;", access=0x0012))  # private final

    ctor = bytearray(b"\x2a")  # aload_0
    ctor += ldc(pool.string("Async Locator")) + category + super_ctor
    for field, label, enabled in (("middleMouse", "Middle Mouse Trigger", True),
                                  ("requireSneak", "Require Sneak", False)):
        ctor += b"\x2a"                                    # aload_0 for putfield
        ctor += instruction(0xbb, pool.clazz("Setting"))    # new Setting
        ctor += b"\x59"                                    # dup
        ctor += ldc(pool.string(label))
        ctor += b"\x04" if enabled else b"\x03"           # iconst_1/0
        ctor += boxed_bool + setting_ctor
        ctor += instruction(0xb5, pool.field("Module_AsyncLocator", field, "LSetting;"))
        ctor += b"\x2a\x2a"                               # this.HwidGen(this.field)
        ctor += instruction(0xb4, pool.field("Module_AsyncLocator", field, "LSetting;"))
        ctor += add_setting
    ctor += b"\x2a" + register + b"\xb1"                 # register(this); return

    methods = [member(pool, "<init>", "()V", access=0x0001, code=bytes(ctor), max_stack=6)]
    for method, field in (("middleMouseEnabled", "middleMouse"),
                          ("requiresSneak", "requireSneak")):
        body = (true_value + b"\x2a" + instruction(0xb4, pool.field("Module_AsyncLocator", field, "LSetting;"))
                + setting_value + equals + b"\xac")      # ireturn
        methods.append(member(pool, method, "()Z", access=0x0001, code=body, max_stack=2))
    methods.append(member(pool, "Module_f", "()V", access=0x0001,
                          code=stop + b"\xb1", max_stack=0))

    return (b"\xca\xfe\xba\xbe" + u2(0) + u2(65)   # Java 21
            + u2(len(pool.entries) + 1) + b"".join(pool.entries)
            + u2(0x0031) + u2(this) + u2(parent) + u2(0)
            + u2(len(fields)) + b"".join(fields)
            + u2(len(methods)) + b"".join(methods) + u2(0))


def make_insta_pearl_class() -> bytes:
    """Small GUI/settings adapter; the timed interaction is in FastPearlCatch.java."""
    pool = Pool()
    name = "Module_InstaPearlCatch"
    this = pool.clazz(name)
    parent = pool.clazz("Module_f")
    category = instruction(0xb2, pool.field("Category", "c", "LCategory;"))
    super_ctor = instruction(0xb7, pool.method("Module_f", "<init>", "(Ljava/lang/String;LCategory;)V"))
    add_setting = instruction(0xb6, pool.method("Module", "HwidGen", "(LSetting;)V"))
    number_ctor = instruction(0xb7, pool.method("Setting", "<init>",
                                               "(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)V"))
    boolean_ctor = instruction(0xb7, pool.method("Setting", "<init>", "(Ljava/lang/String;Ljava/lang/Object;)V"))
    boxed_float = instruction(0xb8, pool.method("java/lang/Float", "valueOf", "(F)Ljava/lang/Float;"))
    boxed_bool = instruction(0xb8, pool.method("java/lang/Boolean", "valueOf", "(Z)Ljava/lang/Boolean;"))
    setting_value = instruction(0xb6, pool.method("Setting", "HwidGen", "()Ljava/lang/Object;"))
    true_value = instruction(0xb2, pool.field("java/lang/Boolean", "TRUE", "Ljava/lang/Boolean;"))
    equals = instruction(0xb6, pool.method("java/lang/Boolean", "equals", "(Ljava/lang/Object;)Z"))
    register = instruction(0xb8, pool.method("com/zelith/integration/FastPearlCatch", "register", "(Ljava/lang/Object;)V"))
    stop = instruction(0xb8, pool.method("com/zelith/integration/FastPearlCatch", "onDisabled", "()V"))

    fields = [member(pool, field, "LSetting;", access=0x0012)
              for field in ("delayTicks", "restoreSlot")]
    ctor = bytearray(b"\x2a")
    ctor += ldc(pool.string("Insta Pearl Catch")) + category + super_ctor
    ctor += b"\x2a" + instruction(0xbb, pool.clazz("Setting")) + b"\x59"
    ctor += ldc(pool.string("Delay Ticks"))
    ctor += b"\x0c" + boxed_float                # 1 tick default
    ctor += b"\x0b" + boxed_float                # 0 tick minimum
    ctor += ldc(pool.float(40.0)) + boxed_float  # 40 ticks = 2 seconds
    ctor += number_ctor
    ctor += instruction(0xb5, pool.field(name, "delayTicks", "LSetting;"))
    ctor += b"\x2a\x2a" + instruction(0xb4, pool.field(name, "delayTicks", "LSetting;")) + add_setting
    ctor += b"\x2a" + instruction(0xbb, pool.clazz("Setting")) + b"\x59"
    ctor += ldc(pool.string("Restore Slot")) + b"\x04" + boxed_bool + boolean_ctor
    ctor += instruction(0xb5, pool.field(name, "restoreSlot", "LSetting;"))
    ctor += b"\x2a\x2a" + instruction(0xb4, pool.field(name, "restoreSlot", "LSetting;")) + add_setting
    ctor += b"\x2a" + register + b"\xb1"

    methods = [member(pool, "<init>", "()V", access=0x0001, code=bytes(ctor), max_stack=8)]
    delay_value = (b"\x2a" + instruction(0xb4, pool.field(name, "delayTicks", "LSetting;"))
                   + setting_value + b"\xb0")  # areturn
    methods.append(member(pool, "delayValue", "()Ljava/lang/Object;", access=0x0001,
                          code=delay_value, max_stack=1))
    restore_value = (true_value + b"\x2a"
                     + instruction(0xb4, pool.field(name, "restoreSlot", "LSetting;"))
                     + setting_value + equals + b"\xac")  # ireturn
    methods.append(member(pool, "restoreSlotEnabled", "()Z", access=0x0001,
                          code=restore_value, max_stack=2))
    methods.append(member(pool, "Module_f", "()V", access=0x0001,
                          code=stop + b"\xb1", max_stack=0))

    return (b"\xca\xfe\xba\xbe" + u2(0) + u2(65)
            + u2(len(pool.entries) + 1) + b"".join(pool.entries)
            + u2(0x0031) + u2(this) + u2(parent) + u2(0)
            + u2(len(fields)) + b"".join(fields)
            + u2(len(methods)) + b"".join(methods) + u2(0))


def make_s_trigger_class() -> bytes:
    """Expose S Trigger's tick hook and settings to Zelith's Combat GUI."""
    pool = Pool()
    name = "Module_STrigger"
    this = pool.clazz(name)
    parent = pool.clazz("Module")  # the normal BIND toggles this always-on module
    category = instruction(0xb2, pool.field("Category", "c", "LCategory;"))
    super_ctor = instruction(0xb7, pool.method("Module", "<init>", "(Ljava/lang/String;LCategory;)V"))
    add_setting = instruction(0xb6, pool.method("Module", "HwidGen", "(LSetting;)V"))
    number_ctor = instruction(0xb7, pool.method("Setting", "<init>",
                                               "(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)V"))
    boolean_ctor = instruction(0xb7, pool.method("Setting", "<init>", "(Ljava/lang/String;Ljava/lang/Object;)V"))
    boxed_float = instruction(0xb8, pool.method("java/lang/Float", "valueOf", "(F)Ljava/lang/Float;"))
    boxed_bool = instruction(0xb8, pool.method("java/lang/Boolean", "valueOf", "(Z)Ljava/lang/Boolean;"))
    setting_value = instruction(0xb6, pool.method("Setting", "HwidGen", "()Ljava/lang/Object;"))
    true_value = instruction(0xb2, pool.field("java/lang/Boolean", "TRUE", "Ljava/lang/Boolean;"))
    equals = instruction(0xb6, pool.method("java/lang/Boolean", "equals", "(Ljava/lang/Object;)Z"))
    service = "com/zelith/integration/STrigger"
    register = instruction(0xb8, pool.method(service, "register", "(Ljava/lang/Object;)V"))
    start = instruction(0xb8, pool.method(service, "onEnabled", "()V"))
    stop = instruction(0xb8, pool.method(service, "onDisabled", "()V"))
    tick = instruction(0xb8, pool.method(service, "tick", "()V"))

    def float_arg(value: float) -> bytes:
        if value == 1.0:
            return b"\x0c" + boxed_float  # fconst_1
        return ldc(pool.float(value)) + boxed_float

    fields = [member(pool, field, "LSetting;", access=0x0012)
              for field in ("hitDelay", "aimFov", "playersOnly")]
    ctor = bytearray(b"\x2a" + ldc(pool.string("S Trigger")) + category + super_ctor)
    for field, label, default, minimum, maximum in (
            ("hitDelay", "Hit Delay Ticks", 10.0, 1.0, 40.0),
            ("aimFov", "Aim FOV", 12.0, 1.0, 45.0)):
        ctor += b"\x2a" + instruction(0xbb, pool.clazz("Setting")) + b"\x59" + ldc(pool.string(label))
        ctor += float_arg(default) + float_arg(minimum) + float_arg(maximum) + number_ctor
        ctor += instruction(0xb5, pool.field(name, field, "LSetting;"))
        ctor += b"\x2a\x2a" + instruction(0xb4, pool.field(name, field, "LSetting;")) + add_setting
    ctor += b"\x2a" + instruction(0xbb, pool.clazz("Setting")) + b"\x59"
    ctor += ldc(pool.string("Players Only")) + b"\x04" + boxed_bool + boolean_ctor
    ctor += instruction(0xb5, pool.field(name, "playersOnly", "LSetting;"))
    ctor += b"\x2a\x2a" + instruction(0xb4, pool.field(name, "playersOnly", "LSetting;")) + add_setting
    ctor += b"\x2a" + register + b"\xb1"

    methods = [member(pool, "<init>", "()V", access=0x0001, code=bytes(ctor), max_stack=8)]
    for field, getter in (("hitDelay", "hitDelayValue"), ("aimFov", "aimFovValue")):
        body = b"\x2a" + instruction(0xb4, pool.field(name, field, "LSetting;")) + setting_value + b"\xb0"
        methods.append(member(pool, getter, "()Ljava/lang/Object;", access=0x0001,
                              code=body, max_stack=1))
    only = (true_value + b"\x2a" + instruction(0xb4, pool.field(name, "playersOnly", "LSetting;"))
            + setting_value + equals + b"\xac")
    methods.append(member(pool, "playersOnlyEnabled", "()Z", access=0x0001,
                          code=only, max_stack=2))
    for name_, body in (("LicenseState", start), ("Module_f", stop), ("Category", tick)):
        methods.append(member(pool, name_, "()V", access=0x0001, code=body + b"\xb1"))

    return (b"\xca\xfe\xba\xbe" + u2(0) + u2(65)
            + u2(len(pool.entries) + 1) + b"".join(pool.entries)
            + u2(0x0031) + u2(this) + u2(parent) + u2(0)
            + u2(len(fields)) + b"".join(fields)
            + u2(len(methods)) + b"".join(methods) + u2(0))


def make_aimbot_class() -> bytes:
    """Expose the smooth camera aim service as a normal toggleable Combat module."""
    pool = Pool()
    name = "Module_Aimbot"
    this = pool.clazz(name)
    parent = pool.clazz("Module")
    category = instruction(0xb2, pool.field("Category", "c", "LCategory;"))
    super_ctor = instruction(0xb7, pool.method("Module", "<init>", "(Ljava/lang/String;LCategory;)V"))
    add_setting = instruction(0xb6, pool.method("Module", "HwidGen", "(LSetting;)V"))
    number_ctor = instruction(0xb7, pool.method("Setting", "<init>",
                                               "(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)V"))
    boolean_ctor = instruction(0xb7, pool.method("Setting", "<init>", "(Ljava/lang/String;Ljava/lang/Object;)V"))
    boxed_float = instruction(0xb8, pool.method("java/lang/Float", "valueOf", "(F)Ljava/lang/Float;"))
    boxed_bool = instruction(0xb8, pool.method("java/lang/Boolean", "valueOf", "(Z)Ljava/lang/Boolean;"))
    setting_value = instruction(0xb6, pool.method("Setting", "HwidGen", "()Ljava/lang/Object;"))
    true_value = instruction(0xb2, pool.field("java/lang/Boolean", "TRUE", "Ljava/lang/Boolean;"))
    equals = instruction(0xb6, pool.method("java/lang/Boolean", "equals", "(Ljava/lang/Object;)Z"))
    service = "com/zelith/integration/Aimbot"
    register = instruction(0xb8, pool.method(service, "register", "(Ljava/lang/Object;)V"))
    start = instruction(0xb8, pool.method(service, "onEnabled", "()V"))
    stop = instruction(0xb8, pool.method(service, "onDisabled", "()V"))
    tick = instruction(0xb8, pool.method(service, "tick", "()V"))

    numeric = (
        ("aimFov", "Aim FOV", 15.0, 1.0, 45.0, "aimFovValue"),
        ("turnSpeed", "Turn Deg/Tick", 3.0, 1.0, 20.0, "turnSpeedValue"),
        ("leadTicks", "Lead Ticks", 2.0, 0.0, 3.0, "leadTicksValue"),
        ("range", "Range Blocks", 16.0, 3.0, 32.0, "rangeValue"),
        ("projectileSpeed", "Projectile Speed", 3.0, 1.0, 4.0, "projectileSpeedValue"),
    )
    boolean = (("playersOnly", "Players Only", "playersOnlyEnabled"),
               ("aimHead", "Aim Head", "aimHeadEnabled"),
               ("holdAttack", "Hold Attack", "holdAttackEnabled"))

    def float_arg(value: float) -> bytes:
        return ({0.0: b"\x0b", 1.0: b"\x0c", 2.0: b"\x0d"}.get(value)
                or ldc(pool.float(value))) + boxed_float

    fields = [member(pool, field, "LSetting;", access=0x0012)
              for field in [*(row[0] for row in numeric), *(row[0] for row in boolean)]]
    ctor = bytearray(b"\x2a" + ldc(pool.string("Aimbot")) + category + super_ctor)
    for field, label, default, minimum, maximum, _ in numeric:
        ctor += b"\x2a" + instruction(0xbb, pool.clazz("Setting")) + b"\x59" + ldc(pool.string(label))
        ctor += float_arg(default) + float_arg(minimum) + float_arg(maximum) + number_ctor
        ctor += instruction(0xb5, pool.field(name, field, "LSetting;"))
        ctor += b"\x2a\x2a" + instruction(0xb4, pool.field(name, field, "LSetting;")) + add_setting
    for field, label, _ in boolean:
        ctor += b"\x2a" + instruction(0xbb, pool.clazz("Setting")) + b"\x59"
        ctor += ldc(pool.string(label)) + b"\x04" + boxed_bool + boolean_ctor
        ctor += instruction(0xb5, pool.field(name, field, "LSetting;"))
        ctor += b"\x2a\x2a" + instruction(0xb4, pool.field(name, field, "LSetting;")) + add_setting
    ctor += b"\x2a" + register + b"\xb1"

    methods = [member(pool, "<init>", "()V", access=0x0001, code=bytes(ctor), max_stack=8)]
    for field, _, _, _, _, getter in numeric:
        body = b"\x2a" + instruction(0xb4, pool.field(name, field, "LSetting;")) + setting_value + b"\xb0"
        methods.append(member(pool, getter, "()Ljava/lang/Object;", access=0x0001,
                              code=body, max_stack=1))
    for field, _, getter in boolean:
        body = (true_value + b"\x2a" + instruction(0xb4, pool.field(name, field, "LSetting;"))
                + setting_value + equals + b"\xac")
        methods.append(member(pool, getter, "()Z", access=0x0001, code=body, max_stack=2))
    for hook, body in (("LicenseState", start), ("Module_f", stop), ("Category", tick)):
        methods.append(member(pool, hook, "()V", access=0x0001, code=body + b"\xb1"))

    return (b"\xca\xfe\xba\xbe" + u2(0) + u2(65)
            + u2(len(pool.entries) + 1) + b"".join(pool.entries)
            + u2(0x0031) + u2(this) + u2(parent) + u2(0)
            + u2(len(fields)) + b"".join(fields)
            + u2(len(methods)) + b"".join(methods) + u2(0))


def generate(output_directory: Path) -> Path:
    output_directory.mkdir(parents=True, exist_ok=True)
    destination = output_directory / "Module_AsyncLocator.class"
    destination.write_bytes(make_module_class())
    (output_directory / "Module_InstaPearlCatch.class").write_bytes(make_insta_pearl_class())
    (output_directory / "Module_STrigger.class").write_bytes(make_s_trigger_class())
    (output_directory / "Module_Aimbot.class").write_bytes(make_aimbot_class())
    return destination
