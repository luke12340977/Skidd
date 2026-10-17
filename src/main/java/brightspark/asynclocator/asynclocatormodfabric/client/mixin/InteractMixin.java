package brightspark.asynclocator.asynclocatormodfabric.client.mixin;

import brightspark.asynclocator.asynclocatormodfabric.client.SilentRot;
import net.fabricmc.api.EnvType;
import net.fabricmc.api.Environment;
import net.minecraft.client.network.ClientPlayerInteractionManager;
import net.minecraft.entity.player.PlayerEntity;
import net.minecraft.util.ActionResult;
import net.minecraft.util.Hand;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Environment(EnvType.CLIENT)
@Mixin({ClientPlayerInteractionManager.class})
public abstract class InteractMixin {
   @Unique
   private boolean al$use;
   @Unique
   private float al$y;
   @Unique
   private float al$p;
   @Unique
   private float al$ly;
   @Unique
   private float al$lp;

   @Inject(
      method = {"interactItem"},
      at = {@At("HEAD")}
   )
   private void al$head(PlayerEntity player, Hand hand, CallbackInfoReturnable<ActionResult> cir) {
      if (SilentRot.on() && !this.al$use) {
         this.al$y = player.getYaw();
         this.al$p = player.getPitch();
         this.al$ly = player.lastYaw;
         this.al$lp = player.lastPitch;
         this.al$use = true;
         float wy = SilentRot.yaw();
         float wp = SilentRot.pitch();
         player.setYaw(wy);
         player.setPitch(wp);
         player.lastYaw = wy;
         player.lastPitch = wp;
      }
   }

   @Inject(
      method = {"interactItem"},
      at = {@At("TAIL")}
   )
   private void al$tail(PlayerEntity player, Hand hand, CallbackInfoReturnable<ActionResult> cir) {
      if (this.al$use) {
         player.setYaw(this.al$y);
         player.setPitch(this.al$p);
         player.lastYaw = this.al$ly;
         player.lastPitch = this.al$lp;
         this.al$use = false;
      }
   }
}
