package com.zelith.integration.mixin;

import com.zelith.integration.AsyncLocatorGate;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/** Keep the original locator algorithm, but prevent it running while OFF. */
@Mixin(targets = "brightspark.asynclocator.asynclocatormodfabric.client.AsyncLocatorClient", remap = false)
public abstract class AsyncLocatorGateMixin {
    @Inject(method = "held()Z", at = @At("RETURN"), cancellable = true)
    private static void integration$held(CallbackInfoReturnable<Boolean> cir) {
        cir.setReturnValue(AsyncLocatorGate.held(cir.getReturnValue()));
    }

    @Inject(method = "onClientTick()V", at = @At("HEAD"))
    private static void integration$beforeTick(CallbackInfo ci) {
        AsyncLocatorGate.beforeTick();
    }

    @Inject(method = "onClientTick()V", at = @At("TAIL"))
    private static void integration$afterTick(CallbackInfo ci) {
        AsyncLocatorGate.afterTick();
    }
}
