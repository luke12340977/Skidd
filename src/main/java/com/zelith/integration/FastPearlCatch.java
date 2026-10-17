package com.zelith.integration;

import brightspark.asynclocator.asynclocatormodfabric.client.mixin.SlotSync;
import java.lang.reflect.Method;
import java.util.Arrays;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.network.ClientPlayerEntity;
import net.minecraft.client.world.ClientWorld;
import net.minecraft.item.Item;
import net.minecraft.item.Items;
import net.minecraft.text.Text;
import net.minecraft.util.ActionResult;
import net.minecraft.util.Hand;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * A one-key pearl -> wind-charge sequence. It does not change the player's
 * camera, invent extra inventory items, or modify server projectile physics.
 */
public final class FastPearlCatch implements ClientModInitializer {
    private static final Logger LOGGER = LoggerFactory.getLogger("zelith-insta-pearl-catch");
    private static final int HOTBAR_SIZE = 9;
    private static final int MAX_DELAY_TICKS = 40;
    private static Object module;
    private static Method enabledMethod;
    private static Method delayMethod;
    private static Method restoreMethod;
    private static Pending pending;

    private record Pending(ClientPlayerEntity player, ClientWorld world, int originalSlot,
                           int expectedSlot, int chargeSlot, Hand chargeHand, int dueAge,
                           boolean restoreSlot) {}

    @Override
    public void onInitializeClient() {
        ClientTickEvents.END_CLIENT_TICK.register(FastPearlCatch::tick);
    }

    // The decompiled Zelith API has public overloads that Java source cannot
    // represent, and its modules live in the default package. Read only the
    // exact boolean module-state method and our generated setting getters.
    public static void register(Object value) {
        try {
            enabledMethod = Arrays.stream(Class.forName("Module").getDeclaredMethods())
                .filter(m -> m.getName().equals("HwidGen") && m.getParameterCount() == 0
                    && m.getReturnType() == boolean.class)
                .findFirst().orElseThrow(() -> new NoSuchMethodException("Module.HwidGen()Z"));
            delayMethod = value.getClass().getMethod("delayValue");
            restoreMethod = value.getClass().getMethod("restoreSlotEnabled");
            module = value;
        } catch (ReflectiveOperationException e) {
            throw new IllegalStateException("Could not register Insta Pearl Catch", e);
        }
    }

    private static boolean enabled() {
        if (module == null) return false;
        try {
            return (boolean) enabledMethod.invoke(module);
        } catch (ReflectiveOperationException e) {
            LOGGER.error("Could not read Insta Pearl Catch state", e);
            return false;
        }
    }

    private static int delayTicks() {
        try {
            Object value = delayMethod.invoke(module);
            int ticks = value instanceof Number number ? Math.round(number.floatValue()) : 1;
            return Math.max(0, Math.min(MAX_DELAY_TICKS, ticks));
        } catch (ReflectiveOperationException e) {
            LOGGER.warn("Could not read Insta Pearl Catch delay; using one tick", e);
            return 1;
        }
    }

    private static boolean restoreSlot() {
        try {
            return (boolean) restoreMethod.invoke(module);
        } catch (ReflectiveOperationException e) {
            LOGGER.warn("Could not read Insta Pearl Catch slot setting; restoring it", e);
            return true;
        }
    }

    /** Called once on the rising edge of the module's ACTIVATION key. */
    public static void trigger() {
        MinecraftClient client = MinecraftClient.getInstance();
        if (!enabled() || pending != null || client.player == null || client.world == null
                || !client.player.isAlive() || client.interactionManager == null
                || client.currentScreen != null) return;

        ClientPlayerEntity player = client.player;
        int originalSlot = player.getInventory().getSelectedSlot();
        int pearlSlot = player.getMainHandStack().isOf(Items.ENDER_PEARL)
            ? originalSlot : hotbarSlot(player, Items.ENDER_PEARL);
        Hand pearlHand = pearlSlot >= 0 ? Hand.MAIN_HAND
            : player.getOffHandStack().isOf(Items.ENDER_PEARL) ? Hand.OFF_HAND : null;
        Hand chargeHand = pearlHand != Hand.OFF_HAND && player.getOffHandStack().isOf(Items.WIND_CHARGE)
            ? Hand.OFF_HAND : Hand.MAIN_HAND;
        int chargeSlot = chargeHand == Hand.MAIN_HAND ? hotbarSlot(player, Items.WIND_CHARGE) : -1;

        // Validate both items before throwing anything. Offhand + main hand
        // and two separate hotbar slots are supported; the rest of inventory
        // is deliberately left alone to avoid unsafe slot-click packets.
        if (pearlHand == null || (chargeHand == Hand.MAIN_HAND && chargeSlot < 0)) {
            notice(client, "Need an ender pearl and wind charge in hotbar/offhand");
            return;
        }
        if (pearlHand == Hand.MAIN_HAND && !select(client, pearlSlot, Items.ENDER_PEARL)) {
            restore(client, originalSlot, player.getInventory().getSelectedSlot());
            notice(client, "Pearl moved before the throw");
            return;
        }
        if (!player.getStackInHand(pearlHand).isOf(Items.ENDER_PEARL)) {
            restore(client, originalSlot, player.getInventory().getSelectedSlot());
            return;
        }

        ActionResult pearlUse = client.interactionManager.interactItem(player, pearlHand);
        if (!pearlUse.isAccepted()) {
            restore(client, originalSlot, player.getInventory().getSelectedSlot());
            notice(client, "Pearl use blocked (check cooldown and server rules)");
            return;
        }
        int expectedSlot = player.getInventory().getSelectedSlot();
        int ticks = delayTicks();
        Pending sequence = new Pending(player, client.world, originalSlot, expectedSlot,
            chargeSlot, chargeHand, player.age + ticks, restoreSlot());
        if (ticks == 0) {
            boolean fired = fireCharge(client, sequence);
            if (!fired) notice(client, "Wind charge unavailable");
            if (sequence.restoreSlot() || !fired) {
                restore(client, sequence.originalSlot(), player.getInventory().getSelectedSlot());
            }
        } else {
            pending = sequence;
        }
    }

    private static void tick(MinecraftClient client) {
        Pending sequence = pending;
        if (sequence == null) return;
        if (!enabled() || client.player != sequence.player() || client.world != sequence.world()
                || !sequence.player().isAlive() || client.interactionManager == null
                || client.currentScreen != null) {
            onDisabled();
            return;
        }
        // If the player deliberately changed slots, do not override their
        // choice or later fire a charge from a surprise slot.
        if (sequence.player().getInventory().getSelectedSlot() != sequence.expectedSlot()) {
            pending = null;
            return;
        }
        if (sequence.player().age < sequence.dueAge()) return;

        pending = null;
        boolean fired = fireCharge(client, sequence);
        if (!fired) notice(client, "Wind charge unavailable");
        if (sequence.restoreSlot() || !fired) {
            // fireCharge may have selected a hotbar slot before discovering
            // that its stack changed. This is still our own selection, so
            // restore it even on failure.
            restore(client, sequence.originalSlot(), sequence.player().getInventory().getSelectedSlot());
        }
    }

    private static boolean fireCharge(MinecraftClient client, Pending sequence) {
        ClientPlayerEntity player = client.player;
        if (player != sequence.player() || client.world != sequence.world()
                || client.interactionManager == null) return false;
        if (sequence.chargeHand() == Hand.MAIN_HAND) {
            if (!select(client, sequence.chargeSlot(), Items.WIND_CHARGE)) return false;
        } else if (!player.getOffHandStack().isOf(Items.WIND_CHARGE)) {
            return false;
        }
        return client.interactionManager.interactItem(player, sequence.chargeHand()).isAccepted();
    }

    private static int hotbarSlot(ClientPlayerEntity player, Item item) {
        if (player.getMainHandStack().isOf(item)) {
            return player.getInventory().getSelectedSlot();
        }
        for (int slot = 0; slot < HOTBAR_SIZE; slot++) {
            if (player.getInventory().getStack(slot).isOf(item)) return slot;
        }
        return -1;
    }

    private static boolean select(MinecraftClient client, int slot, Item item) {
        if (slot < 0 || slot >= HOTBAR_SIZE || client.player == null
                || client.interactionManager == null
                || !client.player.getInventory().getStack(slot).isOf(item)) return false;
        client.player.getInventory().setSelectedSlot(slot);
        ((SlotSync) client.interactionManager).al$sync();
        return client.player.getMainHandStack().isOf(item);
    }

    private static void restore(MinecraftClient client, int originalSlot, int controlledSlot) {
        if (client.player == null || client.interactionManager == null
                || client.player.getInventory().getSelectedSlot() != controlledSlot
                || originalSlot < 0 || originalSlot >= HOTBAR_SIZE
                || originalSlot == controlledSlot) return;
        client.player.getInventory().setSelectedSlot(originalSlot);
        ((SlotSync) client.interactionManager).al$sync();
    }

    /** Stop a queued charge when the module is toggled off or the world closes. */
    public static void onDisabled() {
        Pending sequence = pending;
        pending = null;
        if (sequence != null) {
            MinecraftClient client = MinecraftClient.getInstance();
            if (client.player == sequence.player() && client.world == sequence.world()) {
                restore(client, sequence.originalSlot(), sequence.expectedSlot());
            }
        }
    }

    private static void notice(MinecraftClient client, String message) {
        if (client.player != null) {
            client.player.sendMessage(Text.literal("Insta Pearl Catch: " + message), true);
        }
    }
}
