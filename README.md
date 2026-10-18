# Zelith Combat integration (Fabric 1.21.11)

**Target: Minecraft 1.21.11 with Fabric.** The original Zelith and Async Locator archives, build dependencies, merged mod metadata, and compiled artifact all target 1.21.11.

This project builds **one** Fabric mod from the two uploaded decompiler archives. The decompiled Java is not buildable as-is (the decompiler renamed classes without updating their type descriptors, and emitted Java-illegal overloads). `tools/prepare_archives.py` repairs the supplied Zelith class files without executing them and generates four small Combat module adapters against that bytecode-only API. Gradle/Loom bundles the original algorithms, compiles the readable integration/mixins, and remaps the combined JAR for Fabric.

## Build

Requirements: JDK 21+, Python 3.10+, and internet access to Gradle, Fabric Maven, and Minecraft dependencies.

```sh
./gradlew build
# Windows: gradlew.bat build -PpythonExecutable=py
```

The installable file is `build/libs/zelith-combat-integrated-1.0.0.jar` (not a `-dev.jar`). Put **only that JAR** and the matching Fabric API in the Minecraft 1.21.11 `mods` folder. Remove separate Zelith and Async Locator JARs to avoid duplicate mod IDs/classes. This build reads the two ZIP files in the repo; do not remove them.

## In-game controls

Open Zelith with Right Shift. In **Combat**, **Async Locator** behaves like the other modules:

- Left-click toggles it; right-click opens its settings. It is off by default, and its state/settings/binds are saved in Zelith's config.
- **BIND** toggles the module. **ACTIVATION** runs the locator once when the module is on. The original middle-mouse key also runs it by default; turn **Middle Mouse Trigger** off to use only the ACTIVATION bind.
- **Require Sneak** restricts either trigger to when the player is sneaking. The locator still requires an ender pearl and wind charge in the hotbar, as in the uploaded mod.
- Turning the module off stops an in-progress locator action and releases its silent rotation.

**Combat → Insta Pearl Catch** is a separate, faster one-key module:

- Left-click it **ON**, right-click it, and set the **ACTIVATION** key. Pressing that key throws a pearl, then uses a wind charge. **BIND** is only for toggling the module; leave it unbound if you only need the action key.
- It uses an ender pearl and a wind charge from the hotbar, or one from the offhand when available. It checks for both before throwing and never uses an arbitrary inventory slot.
- **Delay Ticks** is 1 by default (about 0.05 seconds); set it from 0 (same client tick) to 40 (about 2 seconds). **Restore Slot** returns to the previously selected hotbar slot, unless you deliberately change slots before the charge fires.
- This is a fast-use macro, not automatic aim or a server-side collision fix. Catch success still depends on your aim, latency and server timing. Disabling the module or opening a screen cancels a queued charge.

**Combat → S Trigger** is a separate automatic attack module:

- Left-click to enable it; use **BIND** to assign a toggle key. It selects a target near the crosshair and briefly sends its aim to the server before attacking, then restores the server look direction. **Your camera does not turn.** It does not need an ACTIVATION key.
- **Hit Delay Ticks** defaults to 10 (about 0.5 seconds), with a range of 1–40. This is the *minimum* interval between hits; normal weapon cooldown is also respected. **Aim FOV** defaults to 12° (1–45°, measured from the crosshair). **Players Only** defaults to on; turn it off to allow other living entities.
- Attacks stay within 3 blocks and your normal interaction range, require line of sight, and skip invisible entities, teammates and friends when Zelith's **Friends** module and **Anti Triggerbot** setting are enabled. It pauses while you attack manually, use an item or Async Locator controls silent rotation. Avoid enabling the original Triggerbot at the same time.
- The server still sees the temporary look packets. This is **not** an anti-cheat or kick bypass, and a server can reject hits or disconnect you.

**Combat → Aimbot** is a separate smooth camera aim assist, not a triggerbot:

- Left-click to enable, right-click for settings, and use **BIND** to assign a toggle key. It **does not fire or send silent-look packets**; it turns your visible camera toward a target. **Hold Attack** is on by default, so aiming only happens while the attack button is held. Opening a screen or unfocusing the game pauses it.
- **Aim FOV** defaults to 15° (1–45°), **Turn Deg/Tick** to 3 (1–20° per tick), **Range Blocks** to 16 (3–32). It only acquires targets within that view cone and line of sight. **Players Only** defaults on; **Aim Head** aims near eye height by default and can be turned off to aim at the upper chest.
- **Lead Ticks** defaults to 2 (0–3 ticks, roughly 0–150 ms) and extrapolates the target's current velocity. With a bow, crossbow or trident equipped, **Projectile Speed** (default 3 blocks/tick, adjustable 1–4) supplies an *approximate* constant-speed intercept and gravity compensation. Charge level, drag, network latency and server behavior can change the actual hit point.
- It avoids teammates, invisible entities and protected friends when Zelith's **Friends** and **Anti Triggerbot** setting are on; a prediction into a block falls back to the currently visible aim point. It yields to Async Locator's silent rotation. It does **not** automate attacks, fake messages, manipulate statistics, or guarantee avoidance of server kicks or anti-cheat detection.

The GUI's bind rows now use actual keyboard events instead of polling undefined GLFW key codes each rendered frame. Press **Escape** to cancel a bind, **Backspace** to clear one, or another key to save it. This change applies to *all* Zelith modules.

## Validation and caveats

```sh
python3 -m unittest discover -s tests -v
```

These tests verify the repaired class descriptors, all four generated Combat modules, binary entrypoints, integration targets and output reproducibility. **A full 1.21.11 Gradle build passed in GitHub Actions** ([successful run and artifact](https://github.com/luke12340977/Skidd/actions/runs/39011995625)); the sandbox cannot download its JAR from GitHub's separate artifact-storage host. Download the `zelith-combat-integrated` artifact from that run in a browser if needed. **No Minecraft runtime smoke test or 1.21.4 build has passed.** Test the 1.21.11 output in-game before relying on it; if it crashes, supply `latest.log` and the crash report.

The Async Locator upload declares **All Rights Reserved** and includes `LICENSE_async-locator`. Do not redistribute a combined build unless you have permission from its rights holder. The build uses only the two files supplied in this repository; it does not download third-party mod binaries.
