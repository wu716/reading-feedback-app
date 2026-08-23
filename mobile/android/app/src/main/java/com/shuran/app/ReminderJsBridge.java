package com.shuran.app;

import android.util.Log;
import android.webkit.JavascriptInterface;
import android.widget.Toast;

import org.json.JSONObject;

public class ReminderJsBridge {
    private static final String TAG = "ShuranReminder";
    private final MainActivity activity;

    public ReminderJsBridge(MainActivity activity) {
        this.activity = activity;
    }

    @JavascriptInterface
    public boolean isNative() {
        return true;
    }

    @JavascriptInterface
    public boolean hasPermission() {
        return ReminderNotifications.areEnabled(activity);
    }

    @JavascriptInterface
    public void requestPermission() {
        activity.runOnUiThread(activity::requestNotificationPermission);
    }

    @JavascriptInterface
    public void showReminder(String json) {
        try {
            ReminderScheduler.showFromJs(activity.getApplicationContext(), new JSONObject(json));
        } catch (Exception e) {
            Log.e(TAG, "showReminder failed", e);
        }
    }

    /** 测试按钮专用：立刻发一条状态栏通知，不受每日去重/设置开关影响。 */
    @JavascriptInterface
    public String showTestNotification() {
        try {
            if (!ReminderNotifications.areEnabled(activity)) {
                activity.runOnUiThread(activity::requestNotificationPermission);
                activity.runOnUiThread(() -> Toast.makeText(
                        activity,
                        R.string.notification_need_permission,
                        Toast.LENGTH_LONG
                ).show());
                return "no_permission";
            }
            ReminderNotifications.showTest(activity.getApplicationContext());
            activity.runOnUiThread(() -> Toast.makeText(
                    activity,
                    R.string.notification_test_toast,
                    Toast.LENGTH_SHORT
            ).show());
            return "ok";
        } catch (Exception e) {
            Log.e(TAG, "showTestNotification failed", e);
            return "error";
        }
    }

    @JavascriptInterface
    public void syncSession(String json) {
        try {
            JSONObject data = new JSONObject(json);
            ReminderScheduler.syncSession(
                    activity.getApplicationContext(),
                    data.optString("token", ""),
                    data.optString("origin", "")
            );
        } catch (Exception e) {
            Log.e(TAG, "syncSession failed", e);
        }
    }

    @JavascriptInterface
    public void scheduleReminders(String json) {
        try {
            ReminderScheduler.applySettings(activity.getApplicationContext(), new JSONObject(json));
        } catch (Exception e) {
            Log.e(TAG, "scheduleReminders failed", e);
        }
    }

    @JavascriptInterface
    public void scheduleTodos(String json) {
        try {
            ReminderScheduler.applyTodos(activity.getApplicationContext(), new org.json.JSONArray(json));
        } catch (Exception e) {
            Log.e(TAG, "scheduleTodos failed", e);
        }
    }

    @JavascriptInterface
    public boolean canScheduleExactAlarms() {
        return ReminderScheduler.canScheduleExact(activity.getApplicationContext());
    }

    @JavascriptInterface
    public void openExactAlarmSettings() {
        activity.runOnUiThread(activity::openExactAlarmSettings);
    }

    @JavascriptInterface
    public void pollNow() {
        ReminderScheduler.pollNow(activity.getApplicationContext());
    }

    @JavascriptInterface
    public void clearSession() {
        ReminderScheduler.clearSession(activity.getApplicationContext());
    }

    @JavascriptInterface
    public String getAppVersion() {
        return AppUpdater.currentVersionName(activity);
    }

    @JavascriptInterface
    public int getVersionCode() {
        return AppUpdater.currentVersionCode(activity);
    }

    @JavascriptInterface
    public void checkUpdate() {
        activity.runOnUiThread(activity::checkAppUpdateFromUser);
    }
}
