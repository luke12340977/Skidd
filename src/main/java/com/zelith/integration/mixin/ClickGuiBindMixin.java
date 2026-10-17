package com.zelith.integration.mixin;

import com.zelith.integration.BindCapture;
import net.minecraft.client.input.KeyInput;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/** Fixes Zelith's bind crash for every module, not just Async Locator. */
@Mixin(targets = "com.zelith.gui.ClickGUI", remap = false)
public abstract class ClickGuiBindMixin {
    @Inject(method = "pollBindKeys()V", at = @At("HEAD"), cancellable = true)
    private void integration$noUnsafePolling(CallbackInfo ci) {
        ci.cancel();
    }

    @Inject(method = "keyPressed", at = @At("HEAD"), cancellable = true)
    private void integration$captureKey(KeyInput input, CallbackInfoReturnable<Boolean> cir) {
        if (BindCapture.handle(this, input.getKeycode())) {
            cir.setReturnValue(true);
        }
    }

    @Inject(method = "getKeyDisplayNameStatic(I)Ljava/lang/String;",
            at = @At("HEAD"), cancellable = true)
    private static void integration$invalidSavedKey(int code, CallbackInfoReturnable<String> cir) {
        if (code != 0 && !BindCapture.isValidGlfwKey(code)) {
            cir.setReturnValue("");
        }
    }
}
