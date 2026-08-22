package com.shuran.app;

import android.util.Log;
import android.webkit.JavascriptInterface;

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
    public void pollNow() {
        ReminderScheduler.pollNow(activity.getApplicationContext());
    }

    @JavascriptInterface
    public void clearSession() {
        ReminderScheduler.clearSession(activity.getApplicationContext());
    }
}
