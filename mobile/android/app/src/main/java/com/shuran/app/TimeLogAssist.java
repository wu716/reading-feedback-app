package com.shuran.app;

import android.app.Activity;
import android.app.role.RoleManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ShortcutInfo;
import android.content.pm.ShortcutManager;
import android.graphics.drawable.Icon;
import android.os.Build;
import android.provider.Settings;
import android.widget.Toast;

public final class TimeLogAssist {
    public static final String ACTION_PUNCH = "com.shuran.app.PUNCH_TIME_LOG";
    public static final int REQUEST_ASSISTANT_ROLE = 9201;

    private TimeLogAssist() {}

    public static Intent punchIntent(Context context) {
        Intent intent = new Intent(context, TimeLogPunchActivity.class);
        intent.setAction(ACTION_PUNCH);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        return intent;
    }

    public static void launchPunch(Context context) {
        try {
            context.startActivity(punchIntent(context));
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
