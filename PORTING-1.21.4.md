# Full Minecraft 1.21.4 port — not finished

**There is no installable 1.21.4 JAR in this repository.** The uploaded Zelith and Async Locator binaries and their mapping files are for Minecraft **1.21.11**. The successful GitHub Actions artifact is likewise **1.21.11 only**. Changing `minecraft_version` or `fabric.mod.json` to 1.21.4 does not backport the game APIs the original binaries call; Gradle deliberately rejects such an override.

The requested target is **one complete 1.21.4 mod**, retaining Zelith's original GUI and modules, Async Locator's original tracking, the bind fix, and all four Combat entries (Async Locator, Insta Pearl Catch, S Trigger, Aimbot). A standalone Combat replacement or a JAR with disabled original features does **not** meet that target.

## Verified compatibility gaps

The `tools/audit_minecraft_api.py` audit compares the supplied 1.21.11 intermediary → named mapping and the repaired original class files with FabricMC's **complete** 1.21.4 official → intermediary mapping. On the current inputs it scans **179 original classes** and reports **17 absent Minecraft class references** and **35 changed/removed directly declared mapped member references**. Another **206 member references** are inherited/unmapped or constructors and cannot be classified by the mapping comparison alone. These counts are *symbols*, not all runtime failures; some references occur in multiple classes. The audit does not cover Mojang's graphics libraries, Fabric API, mixin injection signatures, or actual game behavior.

Examples that affect features the user asked to preserve:

- The original `ClickGUI` and `ConfigsScreen` reference 1.21.11 `Click`, `KeyInput` and `CharInput`; 1.21.4's `Screen` receives different input method signatures. The existing event-based bind repair also targets the newer signature.
- `DrawContext.getMatrices()` returns a 3×2 stack in the uploaded binaries but a `MatrixStack` in 1.21.4. `DrawContext.drawText` and `drawGuiTexture` descriptors also differ. This affects the original GUI, HUD and notifications.
- Zelith's original rendering references `RenderPipelines`, `RenderLayers`, `UniformType` and sampler/framebuffer APIs not available with those signatures in 1.21.4. Retaining the affected rendering modules requires functional rendering rewrites, not deleting classes.
- Both original client entrypoints refer to the newer `KeyBinding.Category` type. `PlayerInventory.getSelectedSlot()` does not exist with the uploaded binary's signature in 1.21.4; the original locator and other classes need a compatible slot-access implementation.
- The supplied original mixins, Fabric API hooks and the readable Combat/integration classes also need their injection targets and calls checked against 1.21.4. Static mapping checks alone cannot establish that tracking, attacks, GUI interactions and binds still work in-game.

## Reproduce the mapping audit

The mappings are intentionally **not vendored** into this repository. Obtain the complete official mapping from FabricMC's GitHub repository (the Enigma/Yarn source files omit unnamed members and would give misleading results):

```sh
git clone --depth 1 --filter=blob:none --sparse \
  https://github.com/FabricMC/intermediary.git /tmp/skidd-intermediary
git -C /tmp/skidd-intermediary sparse-checkout set --no-cone '/mappings/1.21.4.tiny'
python3 tools/audit_minecraft_api.py \
  --target /tmp/skidd-intermediary/mappings/1.21.4.tiny
```

The audit uses only Python's standard library and never executes an uploaded JAR. It prepares the existing binaries in ignored `build/prepared/` if needed. It cannot replace a 1.21.4 compile, a remapped JAR, or an in-game test.

## Work still required before a 1.21.4 release

1. Backport the original GUI/input and rendering code *without removing features*; remap or rewrite each missing symbol rather than adding a new version string.
2. Adapt the original Async Locator entrypoint/slot access and all original mixins to 1.21.4, preserving its tracking algorithm. Adapt the bind fix and all four Combat modules to the same target mappings.
3. Build and remap against Minecraft 1.21.4, the matching Yarn mappings and Fabric API; update the final metadata constraint **only after** all code and mixins are ported. Keep the existing 1.21.11 build available during this work.
4. Run unit/build checks plus an actual Minecraft 1.21.4 client smoke test of GUI opening, key binding, each original feature and each Combat module before describing a JAR as fully compatible.

The uploaded Async Locator declares **All Rights Reserved**; obtain redistribution permission before publishing a combined binary.
