package com.zelith.integration.mixin;

import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.util.List;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Register before the first GUI is opened; reload the saved module state. */
@Mixin(targets = "SwapHelper", remap = false)
public abstract class RegistryMixin {
    @Inject(method = "Module()V", at = @At("TAIL"))
    private void integration$addCombatModules(CallbackInfo ci) {
        try {
            Method modulesMethod = this.getClass().getMethod("KeyFile");
            @SuppressWarnings("unchecked")
            List<Object> modules = (List<Object>) modulesMethod.invoke(this);
            boolean added = false;
            for (String name : new String[]{"Module_AsyncLocator", "Module_InstaPearlCatch",
                    "Module_STrigger", "Module_Aimbot"}) {
                if (modules.stream().noneMatch(m -> m.getClass().getName().equals(name))) {
                    Constructor<?> constructor = Class.forName(name).getConstructor();
                    modules.add(constructor.newInstance());
                    added = true;
                }
            }
            // Zelith loads its config inside Module(), before a TAIL injection.
            // Reload only after all new modules are registered, so their saved
            // states, binds and settings are applied together.
            if (added) this.getClass().getMethod("Module_ActiveModules").invoke(this);
        } catch (ReflectiveOperationException e) {
            throw new IllegalStateException("Could not add Combat modules to Zelith", e);
        }
    }
}
