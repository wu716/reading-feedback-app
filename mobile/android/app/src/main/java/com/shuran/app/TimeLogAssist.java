package com.shuran.app;

import android.app.Activity;
import android.app.role.RoleManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ShortcutInfo;
import android.content.pm.ShortcutManager;
import android.graphics.drawable.Icon;
import android.os.Build;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.provider.Settings;
import android.widget.Toast;

public final class TimeLogAssist {
    public static final String ACTION_PUNCH = "com.shuran.app.PUNCH_TIME_LOG";
    public static final int REQUEST_ASSISTANT_ROLE = 9201;

    private TimeLogAssist() {}

    public static Intent punchIntent(Context context) {
        Intent intent = new Intent(context, TimeLogPunchActivity.class);
        intent.setAction(ACTION_PUNCH);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK
                | Intent.FLAG_ACTIVITY_CLEAR_TOP
                | Intent.FLAG_ACTIVITY_EXCLUDE_FROM_RECENTS);
        return intent;
    }

    public static void launchPunch(Context context) {
        try {
            context.startActivity(punchIntent(context));
        } catch (Exception ignored) {
        }
    }

    @SuppressWarnings("deprecation")
    public static void buzz(Context context) {
        try {
            Vibrator vibrator = (Vibrator) context.getSystemService(Context.VIBRATOR_SERVICE);
            if (vibrator == null || !vibrator.hasVibrator()) {
                return;
            }
            if (Build.VERSION.SDK_INT >= 26) {
                vibrator.vibrate(VibrationEffect.createOneShot(36, VibrationEffect.DEFAULT_AMPLITUDE));
            } else {
                vibrator.vibrate(36);
            }
        } catch (Exception ignored) {
        }
    }

    public static boolean isAssistantHeld(Context context) {
        if (Build.VERSION.SDK_INT < 29) {
            return false;
        }
        try {
            RoleManager manager = context.getSystemService(RoleManager.class);
            return manager != null && manager.isRoleHeld(RoleManager.ROLE_ASSISTANT);
        } catch (Exception e) {
            return false;
        }
    }

    public static void requestAssistantRole(Activity activity) {
        android.app.AlertDialog.Builder builder = new android.app.AlertDialog.Builder(activity);
        builder.setTitle(R.string.timelog_honor_dialog_title);
        builder.setMessage(R.string.timelog_honor_dialog_body);
        builder.setPositiveButton(R.string.timelog_go_settings, (dialog, which) -> startAssistantSettings(activity));
        builder.setNegativeButton(android.R.string.cancel, null);
        builder.show();
    }

    private static void startAssistantSettings(Activity activity) {
        if (Build.VERSION.SDK_INT >= 29) {
            try {
                RoleManager manager = activity.getSystemService(RoleManager.class);
                if (manager != null
                        && manager.isRoleAvailable(RoleManager.ROLE_ASSISTANT)
                        && !manager.isRoleHeld(RoleManager.ROLE_ASSISTANT)) {
                    activity.startActivityForResult(
                            manager.createRequestRoleIntent(RoleManager.ROLE_ASSISTANT),
                            REQUEST_ASSISTANT_ROLE
                    );
                    return;
                }
            } catch (Exception ignored) {
            }
        }
        openVoiceSettings(activity);
    }

    public static void openVoiceSettings(Context context) {
        Intent[] candidates = new Intent[] {
                new Intent(Settings.ACTION_VOICE_INPUT_SETTINGS),
                new Intent(Settings.ACTION_MANAGE_DEFAULT_APPS_SETTINGS),
                new Intent(Settings.ACTION_SETTINGS)
        };
        for (Intent intent : candidates) {
            try {
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                context.startActivity(intent);
                return;
            } catch (Exception ignored) {
            }
        }
    }

    public static boolean isVolumeKeyServiceEnabled(Context context) {
        String enabled = Settings.Secure.getString(
                context.getContentResolver(),
                Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
        );
        if (enabled == null || enabled.isEmpty()) {
            return false;
        }
        String full = context.getPackageName() + "/" + TimeLogVolumeKeyService.class.getName();
        String compact = context.getPackageName() + "/.TimeLogVolumeKeyService";
        for (String item : enabled.split(":")) {
            if (full.equalsIgnoreCase(item) || compact.equalsIgnoreCase(item)) {
                return true;
            }
        }
        return false;
    }

    public static void openAccessibilitySettings(Context context) {
        try {
            Intent intent = new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS);
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(intent);
        } catch (Exception e) {
            try {
                context.startActivity(new Intent(Settings.ACTION_SETTINGS)
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            } catch (Exception ignored) {
            }
        }
    }

    public static void requestVolumeKeyAccess(Activity activity) {
        android.app.AlertDialog.Builder builder = new android.app.AlertDialog.Builder(activity);
        builder.setTitle(R.string.timelog_volume_dialog_title);
        builder.setMessage(R.string.timelog_volume_dialog_body);
        builder.setPositiveButton(R.string.timelog_go_settings, (dialog, which) -> {
            Toast.makeText(activity, R.string.timelog_volume_settings_toast, Toast.LENGTH_LONG).show();
            openAccessibilitySettings(activity);
        });
        builder.setNegativeButton(android.R.string.cancel, null);
        builder.show();
    }

    public static void requestDisableVolumeKey(Activity activity) {
        Toast.makeText(activity, R.string.timelog_volume_disable_toast, Toast.LENGTH_LONG).show();
        openAccessibilitySettings(activity);
    }

    public static void pinShortcut(Activity activity) {
        if (Build.VERSION.SDK_INT < 26) {
            Toast.makeText(activity, R.string.timelog_shortcut_unsupported, Toast.LENGTH_LONG).show();
            return;
        }
        ShortcutManager manager = activity.getSystemService(ShortcutManager.class);
        if (manager == null || !manager.isRequestPinShortcutSupported()) {
            Toast.makeText(activity, R.string.timelog_shortcut_unsupported, Toast.LENGTH_LONG).show();
            return;
        }
        ShortcutInfo shortcut = new ShortcutInfo.Builder(activity, "timelog_punch")
                .setShortLabel(activity.getString(R.string.timelog_shortcut_short))
                .setLongLabel(activity.getString(R.string.timelog_shortcut_long))
                .setIcon(Icon.createWithResource(activity, R.drawable.ic_timelog))
                .setIntent(new Intent(activity, TimeLogPunchActivity.class).setAction(ACTION_PUNCH))
                .build();
        manager.requestPinShortcut(shortcut, null);
    }
}
