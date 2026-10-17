package com.zelith.integration;

import brightspark.asynclocator.asynclocatormodfabric.client.SilentRot;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Arrays;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.network.ClientPlayNetworkHandler;
import net.minecraft.client.network.ClientPlayerEntity;
import net.minecraft.client.world.ClientWorld;
import net.minecraft.entity.LivingEntity;
import net.minecraft.entity.player.PlayerEntity;
import net.minecraft.network.packet.c2s.play.PlayerMoveC2SPacket;
import net.minecraft.util.Hand;
import net.minecraft.util.math.Box;
import net.minecraft.util.math.MathHelper;
import net.minecraft.util.math.Vec3d;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Small-FOV triggerbot with a temporary server look packet for each hit.
 * The local camera is never changed. This does not bypass server rules.
 */
public final class STrigger {
    private static final Logger LOGGER = LoggerFactory.getLogger("zelith-s-trigger");
    private static final double MAX_REACH = 3.0;
    private static final int MAX_DELAY_TICKS = 40;
    private static final float MAX_FOV_DEGREES = 45.0F;
    private static Object module;
    private static Method hitDelayMethod;
    private static Method fovMethod;
    private static Method playersOnlyMethod;
    private static Method antiTriggerbotMethod;
    private static Method friendNameMethod;
    private static boolean warnedSettings;
    private static boolean warnedFriends;
    private static ClientPlayerEntity lastPlayer;
    private static ClientWorld lastWorld;
    private static int nextAttackAge;

    private record Target(LivingEntity entity, float yaw, float pitch, double angle, double distance) {}

    private STrigger() {}

    /** Called by the generated Zelith module when it is registered. */
    public static void register(Object value) {
        try {
            hitDelayMethod = value.getClass().getMethod("hitDelayValue");
            fovMethod = value.getClass().getMethod("aimFovValue");
            playersOnlyMethod = value.getClass().getMethod("playersOnlyEnabled");
            module = value;
        } catch (ReflectiveOperationException e) {
            throw new IllegalStateException("Could not register S Trigger settings", e);
        }
        // Zelith's default-package classes have Java-illegal overloads.
        // Select both friend methods by their full JVM signature, rather
        // than getMethod(name), which can pick the wrong return type.
        try {
            Class<?> friends = Class.forName("Module_Friends");
            antiTriggerbotMethod = Arrays.stream(friends.getDeclaredMethods())
                .filter(m -> m.getName().equals("KeyFile") && m.getParameterCount() == 0
                    && m.getReturnType() == boolean.class && Modifier.isStatic(m.getModifiers()))
                .findFirst().orElseThrow(() -> new NoSuchMethodException("Module_Friends.KeyFile()Z"));
            friendNameMethod = Arrays.stream(friends.getDeclaredMethods())
                .filter(m -> m.getName().equals("HwidGen") && m.getParameterCount() == 1
                    && m.getParameterTypes()[0] == String.class && m.getReturnType() == boolean.class
                    && Modifier.isStatic(m.getModifiers()))
                .findFirst().orElseThrow(() -> new NoSuchMethodException("Module_Friends.HwidGen(String)Z"));
        } catch (ReflectiveOperationException e) {
            LOGGER.warn("Friend checks unavailable; S Trigger will not attack players", e);
        }
    }

    public static void onEnabled() {
        reset();
    }

    public static void onDisabled() {
        reset();
    }

    private static void reset() {
        lastPlayer = null;
        lastWorld = null;
        nextAttackAge = 0;
    }

    /** Called only while this Combat module is enabled by Zelith's tick loop. */
    public static void tick() {
        MinecraftClient client = MinecraftClient.getInstance();
        if (module == null || client.player == null || client.world == null
                || client.interactionManager == null || client.getNetworkHandler() == null
                || client.currentScreen != null) return;
        ClientPlayerEntity player = client.player;
        if (!player.isAlive() || player.isSpectator() || player.isUsingItem()
                || client.options.attackKey.isPressed() || SilentRot.on()) return;
        // Never race Async Locator's own silent rotation, manual attacks, or
        // ordinary Minecraft weapon cooldowns.
        if (lastPlayer != player || lastWorld != client.world) {
            lastPlayer = player;
            lastWorld = client.world;
            nextAttackAge = 0;
        }
        if (player.age < nextAttackAge || player.getAttackCooldownProgress(0.0F) < 0.99F) return;

        double reach = Math.min(MAX_REACH, player.getEntityInteractionRange());
        if (!Double.isFinite(reach) || reach <= 0.0) return;
        Target target = findTarget(client, player, reach);
        if (target == null) return;
        attack(client, player, target);
    }

    private static Target findTarget(MinecraftClient client, ClientPlayerEntity player, double reach) {
        Vec3d eye = player.getEyePos();
        Vec3d facing = player.getRotationVec(1.0F);
        double minAngle = Math.cos(Math.toRadians(aimFov()));
        boolean onlyPlayers = playersOnly();
        Target best = null;
        for (LivingEntity entity : client.world.getEntitiesByClass(LivingEntity.class,
                player.getBoundingBox().expand(reach + 1.0), candidate -> candidate != player)) {
            if (!entity.isAlive() || entity.isSpectator() || entity.isInvisibleTo(player)
                    || !player.canSee(entity) || (onlyPlayers && !(entity instanceof PlayerEntity))) continue;
            if (entity instanceof PlayerEntity other
                    && (player.isTeammate(other) || protectedFriend(other))) continue;
            double distance = distanceToBoxSquared(eye, entity.getBoundingBox());
            if (distance > reach * reach) continue;
            Vec3d delta = entity.getEyePos().subtract(eye);
            if (delta.lengthSquared() < 1.0E-6) continue;
            double angle = facing.dotProduct(delta.normalize());
            if (angle < minAngle) continue;
            float yaw = MathHelper.wrapDegrees((float)Math.toDegrees(Math.atan2(delta.z, delta.x)) - 90.0F);
            float pitch = (float)-Math.toDegrees(Math.atan2(delta.y, Math.hypot(delta.x, delta.z)));
            if (best == null || angle > best.angle()
                    || (angle == best.angle() && distance < best.distance())) {
                best = new Target(entity, yaw, pitch, angle, distance);
            }
        }
        return best;
    }

    private static double distanceToBoxSquared(Vec3d eye, Box box) {
        double x = Math.max(0.0, Math.max(box.minX - eye.x, eye.x - box.maxX));
        double y = Math.max(0.0, Math.max(box.minY - eye.y, eye.y - box.maxY));
        double z = Math.max(0.0, Math.max(box.minZ - eye.z, eye.z - box.maxZ));
        return x * x + y * y + z * z;
    }

    private static void attack(MinecraftClient client, ClientPlayerEntity player, Target target) {
        ClientPlayNetworkHandler connection = client.getNetworkHandler();
        if (connection == null) return;
        float realYaw = player.getYaw();
        float realPitch = player.getPitch();
        boolean spoof = Math.abs(MathHelper.wrapDegrees(target.yaw() - realYaw)) > 0.01F
            || Math.abs(target.pitch() - realPitch) > 0.01F;
        if (spoof) {
            connection.sendPacket(new PlayerMoveC2SPacket.LookAndOnGround(
                target.yaw(), target.pitch(), player.isOnGround(), player.horizontalCollision));
        }
        try {
            client.interactionManager.attackEntity(player, target.entity());
            player.swingHand(Hand.MAIN_HAND);
            nextAttackAge = player.age + hitDelayTicks();
        } finally {
            // A spoofed look must not leave the server facing a different
            // direction indefinitely if the local player stops moving.
            if (spoof && client.player == player && client.getNetworkHandler() == connection) {
                connection.sendPacket(new PlayerMoveC2SPacket.LookAndOnGround(
                    realYaw, realPitch, player.isOnGround(), player.horizontalCollision));
            }
        }
    }

    private static boolean protectedFriend(PlayerEntity player) {
        if (antiTriggerbotMethod == null || friendNameMethod == null) return true;
        try {
            return (boolean)antiTriggerbotMethod.invoke(null)
                && (boolean)friendNameMethod.invoke(null, player.getName().getString());
        } catch (ReflectiveOperationException e) {
            if (!warnedFriends) {
                LOGGER.warn("Friend lookup failed; S Trigger will not attack players", e);
                warnedFriends = true;
            }
            return true;
        }
    }

    private static Object setting(Method method, Object fallback) {
        try {
            return method.invoke(module);
        } catch (ReflectiveOperationException e) {
            if (!warnedSettings) {
                LOGGER.warn("S Trigger settings could not be read; using safe defaults", e);
                warnedSettings = true;
            }
            return fallback;
        }
    }

    private static int hitDelayTicks() {
        Object value = setting(hitDelayMethod, 10.0F);
        float raw = value instanceof Number number ? number.floatValue() : 10.0F;
        int ticks = Float.isFinite(raw) ? Math.round(raw) : 10;
        return Math.max(1, Math.min(MAX_DELAY_TICKS, ticks));
    }

    private static float aimFov() {
        Object value = setting(fovMethod, 12.0F);
        float degrees = value instanceof Number number ? number.floatValue() : 12.0F;
        if (!Float.isFinite(degrees)) return 12.0F;
        return Math.max(1.0F, Math.min(MAX_FOV_DEGREES, degrees));
    }

    private static boolean playersOnly() {
        return !Boolean.FALSE.equals(setting(playersOnlyMethod, Boolean.TRUE));
    }
}
