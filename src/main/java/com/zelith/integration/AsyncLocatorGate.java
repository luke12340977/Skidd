package com.zelith.integration;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Arrays;
import net.minecraft.client.MinecraftClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** Bridges the original Async Locator key/algorithm to Zelith's module state. */
public final class AsyncLocatorGate {
    private static final Logger LOGGER = LoggerFactory.getLogger("zelith-async-integration");
    private static volatile Object module;
    private static Method enabledMethod;
    private static Method middleMouseMethod;
    private static Method requireSneakMethod;
    private static boolean pulse;
    private static boolean wasEnabled;

    private AsyncLocatorGate() {}

    // The decompiled Zelith classes are in Java's default package, so they
    // cannot be named from this package. Selecting by return type also avoids
    // their bytecode-only overloads, e.g. HwidGen()Z and HwidGen()Lg;.
    public static void register(Object value) {
        try {
            Class<?> base = Class.forName("Module");
            enabledMethod = Arrays.stream(base.getDeclaredMethods())
                .filter(m -> m.getName().equals("HwidGen") && m.getParameterCount() == 0
                    && m.getReturnType() == boolean.class)
                .findFirst().orElseThrow();
            middleMouseMethod = value.getClass().getMethod("middleMouseEnabled");
            requireSneakMethod = value.getClass().getMethod("requiresSneak");
            module = value;
        } catch (ReflectiveOperationException e) {
            throw new IllegalStateException("Could not register the Zelith Async Locator module", e);
        }
    }

    public static boolean enabled() {
        Object value = module;
        if (value == null) return false;
        try {
            return (boolean) enabledMethod.invoke(value);
        } catch (ReflectiveOperationException e) {
            LOGGER.error("Could not read Async Locator state", e);
            return false;
        }
    }

    private static boolean canTrigger() {
        Object value = module;
        if (value == null || !enabled()) return false;
        try {
            if (!(boolean) requireSneakMethod.invoke(value)) return true;
            MinecraftClient client = MinecraftClient.getInstance();
            return client.player != null && client.player.isSneaking();
        } catch (ReflectiveOperationException e) {
            LOGGER.error("Could not read Async Locator settings", e);
            return false;
        }
    }

    /** Zelith's ACTIVATION bind starts one locator operation, not a toggle. */
    public static void trigger() {
        if (canTrigger()) pulse = true;
    }

    /** Called at the return of the original AsyncLocatorClient.held(). */
    public static boolean held(boolean originalKeyPressed) {
        if (!canTrigger()) return false;
        if (pulse) return true;
        try {
            return originalKeyPressed && (boolean) middleMouseMethod.invoke(module);
        } catch (ReflectiveOperationException e) {
            LOGGER.error("Could not read Async Locator trigger setting", e);
            return false;
        }
    }

    /** Config imports can change module state without invoking onDisable(). */
    public static void beforeTick() {
        boolean now = enabled();
        if (!now && wasEnabled) onDisabled();
        wasEnabled = now;
    }

    /** A bind press is one edge; never keep the synthetic key held next tick. */
    public static void afterTick() {
        pulse = false;
    }

    public static void onDisabled() {
        pulse = false;
        wasEnabled = false;
        try {
            Class<?> locator = Class.forName(
                "brightspark.asynclocator.asynclocatormodfabric.client.AsyncLocatorClient");
            Field field = locator.getDeclaredField("catcher");
            field.setAccessible(true);
            Object catcher = field.get(null);
            invokeNoArgVoid(catcher, "b"); // stop the action state machine
            invokeNoArgVoid(catcher, "c"); // release silent rotation
        } catch (ReflectiveOperationException e) {
            LOGGER.warn("Could not stop Async Locator after disabling it", e);
        }
    }

    private static void invokeNoArgVoid(Object target, String name)
            throws ReflectiveOperationException {
        Method method = Arrays.stream(target.getClass().getDeclaredMethods())
            .filter(m -> m.getName().equals(name) && m.getParameterCount() == 0
                && m.getReturnType() == void.class)
            .findFirst().orElseThrow(() -> new NoSuchMethodException(name + "()V"));
        method.setAccessible(true);
        method.invoke(target);
    }
}
