package com.zelith.integration.mixin;

import com.zelith.integration.AsyncLocatorGate;
import com.zelith.integration.FastPearlCatch;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Other modules keep their existing ACTIVATION behavior. */
@Mixin(targets = "Module_f", remap = false)
public abstract class ActivationBindMixin {
    @Inject(method = "KeyFile()V", at = @At("HEAD"), cancellable = true)
    private void integration$activateCombatAction(CallbackInfo ci) {
        String module = this.getClass().getName();
        if (module.equals("Module_AsyncLocator")) {
            AsyncLocatorGate.trigger();
            ci.cancel();
        } else if (module.equals("Module_InstaPearlCatch")) {
            FastPearlCatch.trigger();
            ci.cancel();
        }
    }
}
