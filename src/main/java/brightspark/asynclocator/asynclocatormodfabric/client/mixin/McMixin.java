package brightspark.asynclocator.asynclocatormodfabric.client.mixin;

import brightspark.asynclocator.asynclocatormodfabric.client.AsyncLocatorClient;
import net.fabricmc.api.EnvType;
import net.fabricmc.api.Environment;
import net.minecraft.client.MinecraftClient;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Environment(EnvType.CLIENT)
@Mixin({MinecraftClient.class})
public class McMixin {
   @Inject(
      method = {"tick"},
      at = {@At("HEAD")}
   )
   private void al$tick(CallbackInfo ci) {
      AsyncLocatorClient.onClientTick();
   }

   @Inject(
      method = {"doItemUse"},
      at = {@At("HEAD")},
      cancellable = true
   )
   private void al$noUse(CallbackInfo ci) {
      if (AsyncLocatorClient.held()) {
         ci.cancel();
      }
   }
}
