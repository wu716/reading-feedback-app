package com.shuran.app;

import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.provider.Settings;

public final class TimeLogOverlay {
    private static final String KEY_ENABLED = "timelog_overlay";

    private TimeLogOverlay() {}

    public static boolean hasPermission(Context context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) {
            return true;
        }
        return Settings.canDrawOverlays(context);
    }

    public static boolean isEnabled(Context context) {
        return ReminderScheduler.prefs(context).getBoolean(KEY_ENABLED, false);
    }

    public static void setEnabled(Context context, boolean enabled) {
        ReminderScheduler.prefs(context).edit().putBoolean(KEY_ENABLED, enabled).apply();
        if (enabled && hasPermission(context)) {
            start(context);
        } else {
            stop(context);
        }
    }

    public static void restore(Context context) {
        if (isEnabled(context) && hasPermission(context)) {
            start(context);
        }
    }

    public static void start(Context context) {
        Intent intent = new Intent(context, TimeLogOverlayService.class);
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent);
            } else {
                context.startService(intent);
            }
        } catch (Exception ignored) {
        }
    }

    public static void stop(Context context) {
        try {
            context.stopService(new Intent(context, TimeLogOverlayService.class));
        } catch (Exception ignored) {
        }
    }
}
