package com.zelith.integration;

import brightspark.asynclocator.asynclocatormodfabric.client.SilentRot;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Arrays;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.network.ClientPlayerEntity;
import net.minecraft.client.world.ClientWorld;
import net.minecraft.entity.LivingEntity;
import net.minecraft.entity.player.PlayerEntity;
import net.minecraft.item.ItemStack;
import net.minecraft.item.Items;
import net.minecraft.util.hit.HitResult;
import net.minecraft.util.math.Box;
import net.minecraft.util.math.MathHelper;
import net.minecraft.util.math.Vec3d;
import net.minecraft.world.RaycastContext;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * A separate, camera-visible aim assist; it never attacks or edits network
 * packets. Smooth rotation, narrow FOV and target checks are usability/safety
 * limits, not a promise to defeat server anti-cheat or vote-kicks.
 */
public final class Aimbot {
    private static final Logger LOGGER = LoggerFactory.getLogger("zelith-aimbot");
    private static Object module;
    private static Method fovMethod;
    private static Method speedMethod;
    private static Method leadMethod;
    private static Method rangeMethod;
    private static Method projectileSpeedMethod;
    private static Method playersOnlyMethod;
    private static Method aimHeadMethod;
    private static Method holdAttackMethod;
    private static Method friendProtectionMethod;
    private static Method friendNameMethod;
    private static boolean warnedSettings;
    private static boolean warnedFriends;
    private static ClientPlayerEntity lastPlayer;
    private static ClientWorld lastWorld;
    private static LivingEntity lockedTarget;

    private Aimbot() {}

    /** The generated default-package module exposes only these safe getters. */
    public static void register(Object value) {
        try {
            fovMethod = value.getClass().getMethod("aimFovValue");
            speedMethod = value.getClass().getMethod("turnSpeedValue");
            leadMethod = value.getClass().getMethod("leadTicksValue");
            rangeMethod = value.getClass().getMethod("rangeValue");
            projectileSpeedMethod = value.getClass().getMethod("projectileSpeedValue");
            playersOnlyMethod = value.getClass().getMethod("playersOnlyEnabled");
            aimHeadMethod = value.getClass().getMethod("aimHeadEnabled");
            holdAttackMethod = value.getClass().getMethod("holdAttackEnabled");
            module = value;
        } catch (ReflectiveOperationException e) {
            throw new IllegalStateException("Could not register Aimbot settings", e);
        }
        // Friends has return-type-only overloads that Java source cannot
        // name. Choose the exact static boolean methods by JVM signature.
        try {
            Class<?> friends = Class.forName("Module_Friends");
            friendProtectionMethod = Arrays.stream(friends.getDeclaredMethods())
                .filter(m -> m.getName().equals("KeyFile") && m.getParameterCount() == 0
                    && m.getReturnType() == boolean.class && Modifier.isStatic(m.getModifiers()))
                .findFirst().orElseThrow(() -> new NoSuchMethodException("Module_Friends.KeyFile()Z"));
            friendNameMethod = Arrays.stream(friends.getDeclaredMethods())
                .filter(m -> m.getName().equals("HwidGen") && m.getParameterCount() == 1
                    && m.getParameterTypes()[0] == String.class && m.getReturnType() == boolean.class
                    && Modifier.isStatic(m.getModifiers()))
                .findFirst().orElseThrow(() -> new NoSuchMethodException("Module_Friends.HwidGen(String)Z"));
        } catch (ReflectiveOperationException e) {
            LOGGER.warn("Friends unavailable; Aimbot will not target players", e);
        }
    }

    public static void onEnabled() {
        reset();
    }

    public static void onDisabled() {
        reset();
    }

    private static void reset() {
        lockedTarget = null;
        lastPlayer = null;
        lastWorld = null;
    }

    /** Zelith calls Category() only for enabled modules on its client tick. */
    public static void tick() {
        MinecraftClient client = MinecraftClient.getInstance();
        if (module == null || client.player == null || client.world == null
                || client.currentScreen != null || !client.isWindowFocused()) {
            lockedTarget = null;
            return;
        }
        ClientPlayerEntity player = client.player;
        if (lastPlayer != player || lastWorld != client.world) {
            lockedTarget = null;
            lastPlayer = player;
            lastWorld = client.world;
        }
        if (!player.isAlive() || player.isSpectator() || SilentRot.on()
                || (holdAttack() && !client.options.attackKey.isPressed())) {
            lockedTarget = null;
            return;
        }

        double range = number(rangeMethod, 16.0F, 3.0F, 32.0F);
        Vec3d eye = player.getEyePos();
        Vec3d facing = player.getRotationVec(1.0F);
        boolean head = booleanSetting(aimHeadMethod);
        boolean playersOnly = booleanSetting(playersOnlyMethod);
        double minDot = Math.cos(Math.toRadians(number(fovMethod, 15.0F, 1.0F, 45.0F)));
        LivingEntity best = null;
        double bestScore = -Double.MAX_VALUE;
        for (LivingEntity entity : client.world.getEntitiesByClass(LivingEntity.class,
                player.getBoundingBox().expand(range + 1.0), candidate -> candidate != player)) {
            if (!validTarget(player, entity, range, playersOnly)) continue;
            Vec3d current = hitPoint(entity, head);
            Vec3d toward = current.subtract(eye);
            if (toward.lengthSquared() < 1.0E-6) continue;
            double dot = facing.dotProduct(toward.normalize());
            if (dot < minDot || !player.canSee(entity)
                    || !clearPath(client.world, player, eye, current)) continue;
            // Slight preference for the already selected target avoids
            // flicker when two players cross the same narrow aim cone.
            double score = dot + (entity == lockedTarget ? 0.005 : 0.0);
            if (score > bestScore) {
                best = entity;
                bestScore = score;
            }
        }
        lockedTarget = best;
        if (best == null) return;
        Vec3d current = hitPoint(best, head);
        Vec3d movement = best.getVelocity(); // blocks per game tick
        if (!finite(movement)) movement = Vec3d.ZERO;
        if (movement.lengthSquared() > 0.64) movement = movement.normalize().multiply(0.8);

        double ticks = number(leadMethod, 2.0F, 0.0F, 3.0F);
        boolean projectile = hasProjectile(player);
        if (projectile) {
            double speed = number(projectileSpeedMethod, 3.0F, 1.0F, 4.0F);
            ticks = Math.max(ticks, interceptTicks(eye, current, movement, speed));
        }
        Vec3d predicted = current.add(movement.multiply(ticks));
        if (projectile) predicted = predicted.add(0.0, 0.025 * ticks * ticks, 0.0);
        // A prediction into a block is not a valid aim point. Fall back to
        // the currently visible point rather than tracking through a wall.
        if (!clearPath(client.world, player, eye, predicted)) predicted = current;
        turnToward(player, eye, predicted, number(speedMethod, 3.0F, 1.0F, 20.0F));
    }

    private static boolean validTarget(ClientPlayerEntity player, LivingEntity entity,
                                       double range, boolean playersOnly) {
        if (!entity.isAlive() || entity.isSpectator() || entity.isInvisibleTo(player)
                || (playersOnly && !(entity instanceof PlayerEntity))) return false;
        if (entity instanceof PlayerEntity other
                && (player.isTeammate(other) || protectedFriend(other))) return false;
        return distanceToBoxSquared(player.getEyePos(), entity.getBoundingBox()) <= range * range;
    }

    private static Vec3d hitPoint(LivingEntity entity, boolean head) {
        if (head) return entity.getEyePos().add(0.0, -0.1, 0.0);
        Box box = entity.getBoundingBox();
        Vec3d center = box.getCenter();
        return new Vec3d(center.x, box.minY + box.getLengthY() * 0.65, center.z);
    }

    private static double distanceToBoxSquared(Vec3d eye, Box box) {
        double x = Math.max(0.0, Math.max(box.minX - eye.x, eye.x - box.maxX));
        double y = Math.max(0.0, Math.max(box.minY - eye.y, eye.y - box.maxY));
        double z = Math.max(0.0, Math.max(box.minZ - eye.z, eye.z - box.maxZ));
        return x * x + y * y + z * z;
    }

    private static boolean clearPath(ClientWorld world, ClientPlayerEntity player,
                                     Vec3d eye, Vec3d point) {
        RaycastContext context = new RaycastContext(eye, point,
            RaycastContext.ShapeType.COLLIDER, RaycastContext.FluidHandling.NONE, player);
        return world.raycast(context).getType() == HitResult.Type.MISS;
    }

    private static boolean hasProjectile(ClientPlayerEntity player) {
        return isProjectile(player.getMainHandStack()) || isProjectile(player.getOffHandStack());
    }

    private static boolean isProjectile(ItemStack stack) {
        return stack.isOf(Items.BOW) || stack.isOf(Items.CROSSBOW) || stack.isOf(Items.TRIDENT);
    }

    /** Constant-speed intercept, approximated without Minecraft's projectile drag. */
    private static double interceptTicks(Vec3d from, Vec3d target, Vec3d velocity, double speed) {
        Vec3d delta = target.subtract(from);
        double a = velocity.lengthSquared() - speed * speed;
        double b = 2.0 * delta.dotProduct(velocity);
        double c = delta.lengthSquared();
        double time = Double.POSITIVE_INFINITY;
        if (Math.abs(a) < 1.0E-8) {
            if (b < -1.0E-8) time = -c / b;
        } else {
            double discriminant = b * b - 4.0 * a * c;
            if (discriminant >= 0.0) {
                double root = Math.sqrt(discriminant);
                double first = (-b - root) / (2.0 * a);
                double second = (-b + root) / (2.0 * a);
                if (first > 0.0) time = first;
                if (second > 0.0) time = Math.min(time, second);
            }
        }
        if (!Double.isFinite(time) || time <= 0.0) time = Math.sqrt(c) / speed;
        return Math.max(0.0, Math.min(20.0, time));
    }

    private static void turnToward(ClientPlayerEntity player, Vec3d from, Vec3d point,
                                   float maxDegreesPerTick) {
        Vec3d delta = point.subtract(from);
        if (delta.lengthSquared() < 1.0E-6) return;
        float yaw = MathHelper.wrapDegrees((float)Math.toDegrees(Math.atan2(delta.z, delta.x)) - 90.0F);
        float pitch = (float)-Math.toDegrees(Math.atan2(delta.y, Math.hypot(delta.x, delta.z)));
        float yawDelta = MathHelper.wrapDegrees(yaw - player.getYaw());
        float pitchDelta = pitch - player.getPitch();
        double magnitude = Math.hypot(yawDelta, pitchDelta);
        if (magnitude < 0.2) return; // do not chase tiny client-side interpolation noise
        double fraction = Math.min(1.0, maxDegreesPerTick / magnitude);
        player.setYaw(player.getYaw() + (float)(yawDelta * fraction));
        player.setPitch(MathHelper.clamp(player.getPitch() + (float)(pitchDelta * fraction), -90.0F, 90.0F));
    }

    private static boolean protectedFriend(PlayerEntity player) {
        if (friendProtectionMethod == null || friendNameMethod == null) return true;
        try {
            return (boolean)friendProtectionMethod.invoke(null)
                && (boolean)friendNameMethod.invoke(null, player.getName().getString());
        } catch (ReflectiveOperationException e) {
            if (!warnedFriends) {
                LOGGER.warn("Friend lookup failed; Aimbot will not target players", e);
                warnedFriends = true;
            }
            return true;
        }
    }

    private static boolean finite(Vec3d vector) {
        return Double.isFinite(vector.x) && Double.isFinite(vector.y) && Double.isFinite(vector.z);
    }

    private static Object setting(Method getter, Object fallback) {
        try {
            return getter.invoke(module);
        } catch (ReflectiveOperationException e) {
            if (!warnedSettings) {
                LOGGER.warn("Aimbot settings unavailable; using defaults", e);
                warnedSettings = true;
            }
            return fallback;
        }
    }

    private static float number(Method getter, float fallback, float minimum, float maximum) {
        Object value = setting(getter, fallback);
        float raw = value instanceof Number number ? number.floatValue() : fallback;
        return Float.isFinite(raw) ? Math.max(minimum, Math.min(maximum, raw)) : fallback;
    }

    private static boolean booleanSetting(Method getter) {
        return !Boolean.FALSE.equals(setting(getter, Boolean.TRUE));
    }
}
