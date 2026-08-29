package com.shuran.app;

import android.annotation.SuppressLint;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.PowerManager;
import android.provider.Settings;

import org.json.JSONObject;

public final class ReminderReliability {
    private static final String[][] AUTOSTART_COMPONENTS = {
            {"com.hihonor.systemmanager", "com.huawei.systemmanager.startupmgr.ui.StartupNormalAppListActivity"},
            {"com.hihonor.systemmanager", "com.huawei.systemmanager.appcontrol.activity.StartupAppControlActivity"},
            {"com.huawei.systemmanager", "com.huawei.systemmanager.startupmgr.ui.StartupNormalAppListActivity"},
            {"com.huawei.systemmanager", "com.huawei.systemmanager.appcontrol.activity.StartupAppControlActivity"},
            {"com.huawei.systemmanager", "com.huawei.systemmanager.optimize.process.ProtectActivity"},
            {"com.miui.securitycenter", "com.miui.permcenter.autostart.AutoStartManagementActivity"},
            {"com.coloros.safecenter", "com.coloros.safecenter.startupapp.StartupAppListActivity"},
            {"com.oplus.safecenter", "com.oplus.safecenter.startupapp.StartupAppListActivity"},
            {"com.vivo.permissionmanager", "com.vivo.permissionmanager.activity.BgStartUpManagerActivity"},
            {"com.iqoo.secure", "com.iqoo.secure.ui.phoneoptimize.BgStartUpManager"},
            {"com.samsung.android.lool", "com.samsung.android.sm.ui.battery.BatteryActivity"},
            {"com.letv.android.letvsafe", "com.letv.android.letvsafe.AutobootManageActivity"},
    };

    private ReminderReliability() {}

    public static boolean isIgnoringBattery(Context context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) {
            return true;
        }
        PowerManager pm = (PowerManager) context.getSystemService(Context.POWER_SERVICE);
        return pm != null && pm.isIgnoringBatteryOptimizations(context.getPackageName());
    }

    public static String statusJson(Context context) {
        JSONObject json = new JSONObject();
        try {
            json.put("native", true);
            json.put("notifications", ReminderNotifications.areEnabled(context));
            json.put("exactAlarms", ReminderScheduler.canScheduleExact(context));
            json.put("batteryIgnored", isIgnoringBattery(context));
        } catch (Exception ignored) {
        }
        return json.toString();
    }

    public static void openNotificationSettings(Context context) {
        Intent intent = new Intent();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            intent.setAction(Settings.ACTION_APP_NOTIFICATION_SETTINGS);
            intent.putExtra(Settings.EXTRA_APP_PACKAGE, context.getPackageName());
        } else {
            intent.setAction(Settings.ACTION_APPLICATION_DETAILS_SETTINGS);
            intent.setData(Uri.parse("package:" + context.getPackageName()));
        }
        startSafe(context, intent);
    }

    @SuppressLint("BatteryLife")
    public static void openBatteryOptimizationSettings(Context context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) {
            openAppDetails(context);
            return;
        }
        if (isIgnoringBattery(context)) {
            try {
                startSafe(context, new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS));
                return;
            } catch (Exception ignored) {
            }
            openAppDetails(context);
            return;
        }
        Intent intent = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS);
        intent.setData(Uri.parse("package:" + context.getPackageName()));
        if (!startSafe(context, intent)) {
            try {
                startSafe(context, new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS));
            } catch (Exception ignored) {
                openAppDetails(context);
            }
        }
    }

    public static void openAutostartSettings(Context context) {
        for (String[] pair : AUTOSTART_COMPONENTS) {
            Intent intent = new Intent();
            intent.setComponent(new ComponentName(pair[0], pair[1]));
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            if (startSafe(context, intent)) {
                return;
            }
        }
        openAppDetails(context);
    }

    public static void openAppDetails(Context context) {
        Intent intent = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS);
        intent.setData(Uri.parse("package:" + context.getPackageName()));
        startSafe(context, intent);
    }

    private static boolean startSafe(Context context, Intent intent) {
        try {
            if (!(context instanceof android.app.Activity)) {
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            }
            context.startActivity(intent);
            return true;
        } catch (Exception e) {
            return false;
        }
    }
}
