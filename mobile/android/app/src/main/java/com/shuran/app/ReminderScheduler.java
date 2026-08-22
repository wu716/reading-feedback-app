package com.shuran.app;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Date;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

public final class ReminderScheduler {
    private static final String TAG = "ShuranReminder";
    private static final String PREFS = "shuran_reminders";
    private static final String KEY_TOKEN = "token";
    private static final String KEY_ORIGIN = "origin";
    private static final String KEY_ENABLED = "enabled";
    private static final String KEY_DAILY_ENABLED = "daily_enabled";
    private static final String KEY_DAILY_TIME = "daily_time";
    private static final String KEY_DAYS = "reminder_days";
    private static final String KEY_SYSTEM = "system_notification";
    private static final String KEY_SHOWN_IDS = "shown_log_ids";
    private static final String KEY_DAILY_SHOWN = "daily_shown_date";

    static final String ACTION_DAILY = "com.shuran.app.REMINDER_DAILY";
    static final String ACTION_POLL = "com.shuran.app.REMINDER_POLL";

    private static final int REQ_DAILY = 41;
    private static final int REQ_POLL = 42;
    private static final long POLL_INTERVAL_MS = 15 * 60 * 1000L;
    private static final Object LOCK = new Object();

    private ReminderScheduler() {}

    static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    static String apiOrigin(Context context) {
        String origin = prefs(context).getString(KEY_ORIGIN, "");
        if (origin == null || origin.isEmpty()) {
            origin = context.getString(R.string.app_url);
        }
        if (origin.endsWith("/")) {
            origin = origin.substring(0, origin.length() - 1);
        }
        return origin;
    }

    public static void restore(Context context) {
        if (!prefs(context).getBoolean(KEY_ENABLED, false)) {
            return;
        }
        if (!prefs(context).getBoolean(KEY_SYSTEM, true)) {
            return;
        }
        scheduleLocked(context);
    }

    public static void syncSession(Context context, String token, String origin) {
        SharedPreferences.Editor editor = prefs(context).edit();
        editor.putString(KEY_TOKEN, token == null ? "" : token);
        if (origin != null && !origin.isEmpty()) {
            String cleaned = origin.endsWith("/") ? origin.substring(0, origin.length() - 1) : origin;
            editor.putString(KEY_ORIGIN, cleaned);
        }
        editor.apply();
    }

    public static void clearSession(Context context) {
        prefs(context).edit()
                .remove(KEY_TOKEN)
                .putBoolean(KEY_ENABLED, false)
                .apply();
        cancelAll(context);
    }

    public static void applySettings(Context context, JSONObject settings) {
        boolean enabled = settings.optBoolean("enabled", false);
        boolean dailyEnabled = settings.optBoolean("dailyEnabled", false);
        boolean system = settings.optBoolean("systemNotification", true);
        String time = settings.optString("dailyTime", "20:00");
        JSONArray days = settings.optJSONArray("reminderDays");
        String daysCsv = days == null ? "0,1,2,3,4,5,6" : joinDays(days);

        prefs(context).edit()
                .putBoolean(KEY_ENABLED, enabled)
                .putBoolean(KEY_DAILY_ENABLED, dailyEnabled)
                .putBoolean(KEY_SYSTEM, system)
                .putString(KEY_DAILY_TIME, time)
                .putString(KEY_DAYS, daysCsv)
                .apply();

        if (!enabled || !system) {
            cancelAll(context);
            return;
        }
        scheduleLocked(context);
    }

    public static void showFromJs(Context context, JSONObject data) {
        synchronized (LOCK) {
            showFromJsLocked(context, data);
        }
    }

    private static void showFromJsLocked(Context context, JSONObject data) {
        boolean force = data.optBoolean("force", false)
                || "test".equals(data.optString("reminder_type", ""));
        if (!force && !prefs(context).getBoolean(KEY_SYSTEM, true)) {
            return;
        }
        int logId = data.optInt("log_id", 0);
        String type = data.optString("reminder_type", "");
        if (!force && shouldSkip(context, logId, type)) {
            return;
        }
        if (isStale(data.optString("triggered_at", ""))) {
            markShown(context, logId, type);
            return;
        }
        String title = data.optString("title", context.getString(R.string.notification_default_title));
        String message = stripHtml(data.optString("message", ""));
        String actionUrl = data.optString("action_url", "/static/self_talk/index.html");
        int notifyId = logId > 0 ? 100000 + logId : (int) (System.currentTimeMillis() % 100000);
        ReminderNotifications.show(context, notifyId, title, message, actionUrl);
        markShown(context, logId, type);
    }

    static void onDailyAlarm(Context context) {
        try {
            if (!canNotify(context) || !isDailyDay(context)) {
                return;
            }
            pollPending(context);
            String today = todayStamp();
            if (!today.equals(prefs(context).getString(KEY_DAILY_SHOWN, ""))) {
                ReminderNotifications.show(
                        context,
                        ReminderNotifications.DAILY_NOTIFICATION_ID,
                        context.getString(R.string.notification_daily_title),
                        context.getString(R.string.notification_daily_body),
                        "/static/self_talk/index.html"
                );
                prefs(context).edit().putString(KEY_DAILY_SHOWN, today).apply();
            }
        } catch (Exception e) {
            Log.e(TAG, "daily alarm failed", e);
        } finally {
            scheduleDaily(context);
        }
    }

    static void onPollAlarm(Context context) {
        try {
            pollPending(context);
        } catch (Exception e) {
            Log.e(TAG, "poll alarm failed", e);
        } finally {
            schedulePoll(context);
        }
    }

    public static void pollNow(final Context context) {
        new Thread(() -> {
            try {
                pollPending(context);
            } catch (Exception e) {
                Log.e(TAG, "pollNow failed", e);
            }
        }, "shuran-reminder-poll").start();
    }

    private static boolean canNotify(Context context) {
        return prefs(context).getBoolean(KEY_ENABLED, false)
                && prefs(context).getBoolean(KEY_SYSTEM, true)
                && ReminderNotifications.areEnabled(context);
    }

    private static void pollPending(Context context) throws Exception {
        if (!canNotify(context)) {
            return;
        }
        String token = prefs(context).getString(KEY_TOKEN, "");
        if (token == null || token.isEmpty()) {
            return;
        }
        URL url = new URL(apiOrigin(context) + "/api/self_talk_reminders/pending");
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        try {
            conn.setRequestMethod("GET");
            conn.setRequestProperty("Authorization", "Bearer " + token);
            conn.setRequestProperty("Accept", "application/json");
            conn.setConnectTimeout(15000);
            conn.setReadTimeout(15000);
            int code = conn.getResponseCode();
            if (code != 200) {
                Log.w(TAG, "pending HTTP " + code);
                return;
            }
            BufferedReader reader = new BufferedReader(
                    new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8)
            );
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) {
                sb.append(line);
            }
            reader.close();
            JSONObject json = new JSONObject(sb.toString());
            JSONArray list = json.optJSONArray("notifications");
            if (list == null) {
                return;
            }
            for (int i = 0; i < list.length(); i++) {
                JSONObject item = list.optJSONObject(i);
                if (item != null) {
                    showFromJs(context, item);
                }
            }
        } finally {
            conn.disconnect();
        }
    }

    private static boolean shouldSkip(Context context, int logId, String type) {
        if (logId > 0 && shownIds(context).contains(String.valueOf(logId))) {
            return true;
        }
        if ("daily".equals(type) && todayStamp().equals(prefs(context).getString(KEY_DAILY_SHOWN, ""))) {
            if (logId > 0) {
                markShown(context, logId, type);
            }
            return true;
        }
        return false;
    }

    private static void markShown(Context context, int logId, String type) {
        if ("daily".equals(type)) {
            prefs(context).edit().putString(KEY_DAILY_SHOWN, todayStamp()).apply();
        }
        if (logId <= 0) {
            return;
        }
        Set<String> ids = shownIds(context);
        ids.add(String.valueOf(logId));
        while (ids.size() > 200) {
            String first = ids.iterator().next();
            ids.remove(first);
        }
        prefs(context).edit().putStringSet(KEY_SHOWN_IDS, ids).apply();
    }

    private static Set<String> shownIds(Context context) {
        Set<String> stored = prefs(context).getStringSet(KEY_SHOWN_IDS, null);
        return stored == null ? new HashSet<String>() : new HashSet<String>(stored);
    }

    private static void scheduleLocked(Context context) {
        schedulePoll(context);
        scheduleDaily(context);
    }

    private static void scheduleDaily(Context context) {
        AlarmManager am = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        if (am == null) {
            return;
        }
        PendingIntent pi = pending(context, ACTION_DAILY, REQ_DAILY);
        if (!prefs(context).getBoolean(KEY_ENABLED, false)
                || !prefs(context).getBoolean(KEY_DAILY_ENABLED, false)
                || !prefs(context).getBoolean(KEY_SYSTEM, true)) {
            am.cancel(pi);
            return;
        }
        long at = nextDailyMillis(context);
        setWakeup(am, at, pi);
    }

    private static void schedulePoll(Context context) {
        AlarmManager am = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        if (am == null) {
            return;
        }
        PendingIntent pi = pending(context, ACTION_POLL, REQ_POLL);
        if (!prefs(context).getBoolean(KEY_ENABLED, false)
                || !prefs(context).getBoolean(KEY_SYSTEM, true)
                || isEmpty(prefs(context).getString(KEY_TOKEN, ""))) {
            am.cancel(pi);
            return;
        }
        long at = System.currentTimeMillis() + POLL_INTERVAL_MS;
        setWakeup(am, at, pi);
    }

    private static void cancelAll(Context context) {
        AlarmManager am = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        if (am == null) {
            return;
        }
        am.cancel(pending(context, ACTION_DAILY, REQ_DAILY));
        am.cancel(pending(context, ACTION_POLL, REQ_POLL));
    }

    private static void setWakeup(AlarmManager am, long at, PendingIntent pi) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            if (am.canScheduleExactAlarms()) {
                am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pi);
                return;
            }
            am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pi);
            return;
        }
        am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pi);
    }

    private static PendingIntent pending(Context context, String action, int requestCode) {
        Intent intent = new Intent(context, ReminderAlarmReceiver.class);
        intent.setAction(action);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            flags |= PendingIntent.FLAG_IMMUTABLE;
        }
        return PendingIntent.getBroadcast(context, requestCode, intent, flags);
    }

    private static long nextDailyMillis(Context context) {
        int[] hm = parseTime(prefs(context).getString(KEY_DAILY_TIME, "20:00"));
        Set<Integer> days = parseDays(prefs(context).getString(KEY_DAYS, "0,1,2,3,4,5,6"));
        Calendar cal = Calendar.getInstance();
        cal.set(Calendar.SECOND, 0);
        cal.set(Calendar.MILLISECOND, 0);
        cal.set(Calendar.HOUR_OF_DAY, hm[0]);
        cal.set(Calendar.MINUTE, hm[1]);
        for (int i = 0; i < 8; i++) {
            int ourDay = cal.get(Calendar.DAY_OF_WEEK) - 1;
            if (days.contains(ourDay) && cal.getTimeInMillis() > System.currentTimeMillis() + 3000) {
                return cal.getTimeInMillis();
            }
            cal.add(Calendar.DAY_OF_MONTH, 1);
            cal.set(Calendar.HOUR_OF_DAY, hm[0]);
            cal.set(Calendar.MINUTE, hm[1]);
        }
        return System.currentTimeMillis() + 24 * 60 * 60 * 1000L;
    }

    private static boolean isDailyDay(Context context) {
        if (!prefs(context).getBoolean(KEY_DAILY_ENABLED, false)) {
            return false;
        }
        Set<Integer> days = parseDays(prefs(context).getString(KEY_DAYS, "0,1,2,3,4,5,6"));
        int ourDay = Calendar.getInstance().get(Calendar.DAY_OF_WEEK) - 1;
        return days.contains(ourDay);
    }

    private static int[] parseTime(String raw) {
        int hour = 20;
        int minute = 0;
        if (raw != null) {
            String[] parts = raw.trim().split(":");
            try {
                if (parts.length >= 1) hour = Integer.parseInt(parts[0]);
                if (parts.length >= 2) minute = Integer.parseInt(parts[1]);
            } catch (NumberFormatException ignored) {
            }
        }
        hour = Math.max(0, Math.min(23, hour));
        minute = Math.max(0, Math.min(59, minute));
        return new int[]{hour, minute};
    }

    private static Set<Integer> parseDays(String csv) {
        Set<Integer> days = new HashSet<>();
        if (csv == null || csv.isEmpty()) {
            for (int i = 0; i < 7; i++) days.add(i);
            return days;
        }
        for (String part : csv.split(",")) {
            try {
                days.add(Integer.parseInt(part.trim()));
            } catch (NumberFormatException ignored) {
            }
        }
        if (days.isEmpty()) {
            for (int i = 0; i < 7; i++) days.add(i);
        }
        return days;
    }

    private static String joinDays(JSONArray days) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < days.length(); i++) {
            if (i > 0) sb.append(',');
            sb.append(days.optInt(i));
        }
        return sb.length() == 0 ? "0,1,2,3,4,5,6" : sb.toString();
    }

    private static String todayStamp() {
        return new SimpleDateFormat("yyyy-MM-dd", Locale.US).format(new Date());
    }

    private static boolean isStale(String iso) {
        if (iso == null || iso.isEmpty()) {
            return false;
        }
        try {
            String trimmed = iso.replace('T', ' ');
            if (trimmed.length() >= 19) {
                trimmed = trimmed.substring(0, 19);
            }
            Date parsed = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).parse(trimmed);
            return parsed != null && System.currentTimeMillis() - parsed.getTime() > 24L * 60 * 60 * 1000;
        } catch (Exception ignored) {
            return false;
        }
    }

    static String stripHtml(String raw) {
        if (raw == null) return "";
        return raw.replaceAll("<[^>]*>", " ").replaceAll("\\s+", " ").trim();
    }

    private static boolean isEmpty(String s) {
        return s == null || s.isEmpty();
    }
}
