package com.zelith.integration;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** Event-driven replacement for ClickGUI.pollBindKeys(). */
public final class BindCapture {
    private static final Logger LOGGER = LoggerFactory.getLogger("zelith-bind-capture");
    private static Field bindField;
    private static Field activationField;

    private BindCapture() {}

    private static void locateFields(Object gui) throws ReflectiveOperationException {
        if (bindField != null && activationField != null) return;
        Class<?> type = gui.getClass();
        Field bind = type.getDeclaredField("listeningBind");
        Field activation = type.getDeclaredField("listeningActivationBind");
        bind.setAccessible(true);
        activation.setAccessible(true);
        bindField = bind;
        activationField = activation;
    }

    /**
     * @return true if the screen is listening and this key event was consumed.
     * Escape cancels, Backspace clears, and any valid key binds once. A raw
     * GLFW key event cannot produce the undefined key codes the old render-
     * time loop passed to glfwGetKey (and crashed on some GLFW installations).
     */
    public static boolean handle(Object gui, int keyCode) {
        try {
            locateFields(gui);
            Object bind = bindField.get(gui);
            Object activation = activationField.get(gui);
            if (bind == null && activation == null) return false;

            if (keyCode == 256) { // ESC: don't close the settings popup
                clear(gui);
                return true;
            }
            if (keyCode != 259 && !isValidGlfwKey(keyCode)) return true;
            int value = keyCode == 259 ? 0 : keyCode;
            if (bind != null) {
                Method setter = bind.getClass().getMethod("c", int.class);
                setter.invoke(bind, value);
            }
            if (activation != null) {
                Method setter = activation.getClass().getMethod("HwidGen", int.class);
                setter.invoke(activation, value);
            }
            clear(gui);
            return true;
        } catch (ReflectiveOperationException e) {
            LOGGER.error("Could not save Zelith key binding; keeping the GUI open", e);
            try {
                clear(gui);
            } catch (ReflectiveOperationException ignored) {
                // If even the screen fields are missing, allow normal GUI input.
            }
            return false;
        }
    }

    private static void clear(Object gui) throws ReflectiveOperationException {
        bindField.set(gui, null);
        activationField.set(gui, null);
    }

    /** GLFW's documented key constants; holes (33-38, etc.) are not keys. */
    public static boolean isValidGlfwKey(int code) {
        return code == 32 || code == 39 || (code >= 44 && code <= 57)
            || code == 59 || code == 61 || (code >= 65 && code <= 93)
            || code == 96 || code == 161 || code == 162
            || (code >= 256 && code <= 269)
            || (code >= 280 && code <= 284)
            || (code >= 290 && code <= 314)
            || (code >= 320 && code <= 336)
            || (code >= 340 && code <= 348);
    }
}
