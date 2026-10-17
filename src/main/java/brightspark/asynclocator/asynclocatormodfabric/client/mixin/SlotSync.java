package brightspark.asynclocator.asynclocatormodfabric.client.mixin;

import net.fabricmc.api.EnvType;
import net.fabricmc.api.Environment;
import net.minecraft.client.network.ClientPlayerInteractionManager;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Invoker;

@Environment(EnvType.CLIENT)
@Mixin({ClientPlayerInteractionManager.class})
public interface SlotSync {
   @Invoker("syncSelectedSlot")
   void al$sync();
}
