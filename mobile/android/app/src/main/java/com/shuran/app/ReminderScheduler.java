package com.shuran.app;

import android.app.AlarmManager;
import android.app.Notification;
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
    private static final String KEY_USER_DISABLED = "user_disabled";
    private static final String KEY_DAILY_ENABLED = "daily_enabled";
    private static final String KEY_DAILY_TIME = "daily_time";
    private static final String KEY_DAYS = "reminder_days";
    private static final String KEY_SYSTEM = "system_notification";
    private static final String KEY_SHOWN_IDS = "shown_log_ids";
    private static final String KEY_DAILY_SHOWN = "daily_shown_date";
    private static final String KEY_READING_ENABLED = "reading_enabled";
    private static final String KEY_READING_TIME = "reading_time";
    private static final String KEY_READING_SHOWN = "reading_shown_date";
    private static final String KEY_TODOS_JSON = "todos_json";

    static final String ACTION_DAILY = "com.shuran.app.REMINDER_DAILY";
    static final String ACTION_POLL = "com.shuran.app.REMINDER_POLL";
    static final String ACTION_READING = "com.shuran.app.REMINDER_READING";
    static final String ACTION_TODO = "com.shuran.app.REMINDER_TODO";
    static final String ACTION_TEST = "com.shuran.app.REMINDER_TEST";
    static final String EXTRA_TODO_ID = "todo_id";
    static final String EXTRA_TODO_TEXT = "todo_text";

    private static final int REQ_DAILY = 41;
    private static final int REQ_POLL = 42;
    private static final int REQ_READING = 43;
    private static final int REQ_TEST = 44;
    private static final int REQ_DAILY_SHOW = 141;
    private static final int REQ_READING_SHOW = 143;
    private static final int REQ_TEST_SHOW = 144;
    private static final int TODO_REQ_BASE = 10000;
    private static final int TODO_SHOW_BASE = 30000;
    private static final long POLL_INTERVAL_MS = 15 * 60 * 1000L;
    private static final Object LOCK = new Object();

    private ReminderScheduler() {}

    static final class Delivery {
        boolean userVisible;
        boolean poll;
        int notificationId;
        Notification notification;
    }

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
        SharedPreferences p = prefs(context);
        if (!p.getBoolean(KEY_SYSTEM, true)) {
            return;
        }
        boolean enabled = p.getBoolean(KEY_ENABLED, false);
        boolean hasLocal = p.getBoolean(KEY_DAILY_ENABLED, false)
                || p.getBoolean(KEY_READING_ENABLED, false)
                || hasStoredTodos(p);
        // 旧版 401/登出曾把 enabled 清掉但留下时间；升级后自动恢复，不要求当天再登录。
        if (!enabled && hasLocal && !p.getBoolean(KEY_USER_DISABLED, false)) {
            p.edit().putBoolean(KEY_ENABLED, true).apply();
            enabled = true;
            Log.i(TAG, "restored enabled from persisted local reminders");
        }
        if (!enabled && !hasLocal) {
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

    /** 只清 token，不清闹钟。登录过期后本地到点提醒仍要响。 */
    public static void clearSession(Context context) {
        prefs(context).edit().remove(KEY_TOKEN).apply();
    }

    public static void applySettings(Context context, JSONObject settings) {
        SharedPreferences p = prefs(context);
        boolean enabled = settings.has("enabled")
                ? settings.optBoolean("enabled", false)
                : p.getBoolean(KEY_ENABLED, false);
        boolean dailyEnabled = settings.has("dailyEnabled")
                ? settings.optBoolean("dailyEnabled", false)
                : p.getBoolean(KEY_DAILY_ENABLED, false);
        boolean system = settings.has("systemNotification")
                ? settings.optBoolean("systemNotification", true)
                : p.getBoolean(KEY_SYSTEM, true);
        String time = settings.has("dailyTime")
                ? settings.optString("dailyTime", "20:00")
                : p.getString(KEY_DAILY_TIME, "20:00");
        JSONArray days = settings.optJSONArray("reminderDays");
        String daysCsv = days == null
                ? p.getString(KEY_DAYS, "0,1,2,3,4,5,6")
                : joinDays(days);
        boolean readingEnabled = settings.has("readingEnabled")
                ? settings.optBoolean("readingEnabled", false)
                : p.getBoolean(KEY_READING_ENABLED, false);
        String readingTime = settings.has("readingTime")
                ? settings.optString("readingTime", "21:00")
                : p.getString(KEY_READING_TIME, "21:00");

        SharedPreferences.Editor editor = p.edit()
                .putBoolean(KEY_ENABLED, enabled)
                .putBoolean(KEY_DAILY_ENABLED, dailyEnabled)
                .putBoolean(KEY_SYSTEM, system)
                .putString(KEY_DAILY_TIME, time)
                .putString(KEY_DAYS, daysCsv)
                .putBoolean(KEY_READING_ENABLED, readingEnabled)
                .putString(KEY_READING_TIME, readingTime);
        if (settings.has("enabled")) {
            editor.putBoolean(KEY_USER_DISABLED, !enabled);
        }
        editor.apply();

        if (!system) {
            cancelAll(context);
            return;
        }
        if (settings.has("enabled") && !enabled) {
            cancelAll(context);
            return;
        }
        if (!prefs(context).getBoolean(KEY_ENABLED, false)
                && !prefs(context).getBoolean(KEY_USER_DISABLED, false)) {
            prefs(context).edit().putBoolean(KEY_ENABLED, true).apply();
        }
        scheduleLocked(context);
    }

    public static void applyTodos(Context context, JSONArray todos) {
        cancelTodoAlarms(context);
        prefs(context).edit().putString(KEY_TODOS_JSON, todos == null ? "[]" : todos.toString()).apply();
        if (!prefs(context).getBoolean(KEY_SYSTEM, true)) {
            return;
        }
        if (!prefs(context).getBoolean(KEY_ENABLED, false)
                && prefs(context).getBoolean(KEY_USER_DISABLED, false)) {
            return;
        }
        scheduleTodos(context);
    }

    public static boolean canScheduleExact(Context context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) {
            return true;
        }
        AlarmManager am = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        return am != null && am.canScheduleExactAlarms();
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

    /**
     * 闹钟到点：立刻组本地通知并登记下一次。不依赖 token / 登录 / 服务器 pending。
     */
    static Delivery deliverLocal(Context context, Intent intent) {
        Delivery delivery = new Delivery();
        String action = intent == null ? null : intent.getAction();
        try {
            if (ACTION_DAILY.equals(action)) {
                fillDaily(context, delivery);
                scheduleDaily(context);
            } else if (ACTION_READING.equals(action)) {
                fillReading(context, delivery);
                scheduleReading(context);
            } else if (ACTION_TODO.equals(action)) {
                fillTodo(context, intent, delivery);
            } else if (ACTION_TEST.equals(action)) {
                fillTest(context, delivery);
            } else if (ACTION_POLL.equals(action)) {
                delivery.poll = true;
                schedulePoll(context);
            }
        } catch (Exception e) {
            Log.e(TAG, "deliverLocal failed", e);
            if (ACTION_DAILY.equals(action)) {
                scheduleDaily(context);
            } else if (ACTION_READING.equals(action)) {
                scheduleReading(context);
            } else if (ACTION_POLL.equals(action)) {
                schedulePoll(context);
            }
        }
        return delivery;
    }

    private static void fillDaily(Context context, Delivery delivery) {
        delivery.userVisible = true;
        delivery.poll = true;
        delivery.notificationId = ReminderNotifications.DAILY_NOTIFICATION_ID;
        delivery.notification = ReminderNotifications.build(
                context,
                context.getString(R.string.notification_daily_title),
                context.getString(R.string.notification_daily_body),
                "/static/self_talk/index.html"
        );
        if (!ReminderNotifications.areEnabled(context)) {
            Log.w(TAG, "daily alarm fired but notifications disabled");
            return;
        }
        Set<Integer> days = parseDays(prefs(context).getString(KEY_DAYS, "0,1,2,3,4,5,6"));
        int ourDay = Calendar.getInstance().get(Calendar.DAY_OF_WEEK) - 1;
        if (!days.contains(ourDay)) {
            return;
        }
        String today = todayStamp();
        if (!today.equals(prefs(context).getString(KEY_DAILY_SHOWN, ""))) {
            ReminderNotifications.showPrepared(
                    context,
                    delivery.notificationId,
                    delivery.notification
            );
            prefs(context).edit().putString(KEY_DAILY_SHOWN, today).apply();
        }
    }

    private static void fillReading(Context context, Delivery delivery) {
        delivery.userVisible = true;
        delivery.notificationId = ReminderNotifications.READING_NOTIFICATION_ID;
        delivery.notification = ReminderNotifications.build(
                context,
                context.getString(R.string.notification_reading_title),
                context.getString(R.string.notification_reading_body),
                "/static/index.html#overview"
        );
        if (!ReminderNotifications.areEnabled(context)) {
            Log.w(TAG, "reading alarm fired but notifications disabled");
            return;
        }
        String today = todayStamp();
        if (!today.equals(prefs(context).getString(KEY_READING_SHOWN, ""))) {
            ReminderNotifications.showPrepared(
                    context,
                    delivery.notificationId,
                    delivery.notification
            );
            prefs(context).edit().putString(KEY_READING_SHOWN, today).apply();
        }
    }

    private static void fillTodo(Context context, Intent intent, Delivery delivery) {
        int todoId = intent == null ? 0 : intent.getIntExtra(EXTRA_TODO_ID, 0);
        String text = intent == null ? null : intent.getStringExtra(EXTRA_TODO_TEXT);
        if (text == null || text.trim().isEmpty()) {
            text = context.getString(R.string.notification_todo_fallback);
        }
        delivery.userVisible = true;
        delivery.notificationId = todoId > 0 ? 200000 + todoId : (int) (System.currentTimeMillis() % 100000);
        delivery.notification = ReminderNotifications.build(
                context,
                context.getString(R.string.notification_todo_title),
                text,
                "/static/index.html#overview"
        );
        if (!ReminderNotifications.areEnabled(context)) {
            Log.w(TAG, "todo alarm fired but notifications disabled");
            return;
        }
        ReminderNotifications.showPrepared(context, delivery.notificationId, delivery.notification);
    }

    private static void fillTest(Context context, Delivery delivery) {
        delivery.userVisible = true;
        delivery.notificationId = ReminderNotifications.TEST_NOTIFICATION_ID;
        delivery.notification = ReminderNotifications.build(
                context,
                context.getString(R.string.notification_test_title),
                context.getString(R.string.notification_exit_test_body),
                "/static/index.html#user-center"
        );
        ReminderNotifications.showPrepared(context, delivery.notificationId, delivery.notification);
    }

    public static boolean scheduleTest(Context context, int seconds) {
        AlarmManager am = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        if (am == null) {
            return false;
        }
        int delay = Math.max(30, Math.min(600, seconds));
        long at = System.currentTimeMillis() + delay * 1000L;
        setWakeup(context, am, at, pending(context, ACTION_TEST, REQ_TEST), REQ_TEST_SHOW, true);
        Log.i(TAG, "scheduled exit test in " + delay + "s");
        return true;
    }

    public static void pollNow(final Context context) {
        new Thread(() -> pollNowBlocking(context), "shuran-reminder-poll").start();
    }

    static void pollNowBlocking(Context context) {
        try {
            pollPending(context);
        } catch (Exception e) {
            Log.e(TAG, "pollNow failed", e);
        }
    }

    private static void pollPending(Context context) throws Exception {
        if (!prefs(context).getBoolean(KEY_SYSTEM, true)
                || !ReminderNotifications.areEnabled(context)) {
            return;
        }
        String token = prefs(context).getString(KEY_TOKEN, "");
        if (token == null || token.isEmpty()) {
            Log.i(TAG, "skip pending poll: no token");
            return;
        }
        URL url = new URL(apiOrigin(context) + "/api/self_talk_reminders/pending");
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        try {
            conn.setRequestMethod("GET");
            conn.setRequestProperty("Authorization", "Bearer " + token);
            conn.setRequestProperty("Accept", "application/json");
            conn.setConnectTimeout(8000);
            conn.setReadTimeout(8000);
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
        scheduleReading(context);
        scheduleTodos(context);
    }

    private static boolean masterOn(Context context) {
        SharedPreferences p = prefs(context);
        if (p.getBoolean(KEY_ENABLED, false)) {
            return true;
        }
        return !p.getBoolean(KEY_USER_DISABLED, false)
                && (p.getBoolean(KEY_DAILY_ENABLED, false)
                || p.getBoolean(KEY_READING_ENABLED, false)
                || hasStoredTodos(p));
    }

    private static void scheduleDaily(Context context) {
        AlarmManager am = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        if (am == null) {
            return;
        }
        PendingIntent pi = pending(context, ACTION_DAILY, REQ_DAILY);
        if (!masterOn(context)
                || !prefs(context).getBoolean(KEY_DAILY_ENABLED, false)
                || !prefs(context).getBoolean(KEY_SYSTEM, true)) {
            am.cancel(pi);
            return;
        }
        long at = nextDailyMillis(context);
        setWakeup(context, am, at, pi, REQ_DAILY_SHOW, true);
        Log.i(TAG, "daily alarm " + formatAt(at));
    }

    private static void schedulePoll(Context context) {
        AlarmManager am = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        if (am == null) {
            return;
        }
        PendingIntent pi = pending(context, ACTION_POLL, REQ_POLL);
        if (!masterOn(context)
                || !prefs(context).getBoolean(KEY_SYSTEM, true)
                || isEmpty(prefs(context).getString(KEY_TOKEN, ""))) {
            am.cancel(pi);
            return;
        }
        long at = System.currentTimeMillis() + POLL_INTERVAL_MS;
        setWakeup(context, am, at, pi, REQ_POLL, false);
    }

    private static void scheduleReading(Context context) {
        AlarmManager am = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        if (am == null) {
            return;
        }
        PendingIntent pi = pending(context, ACTION_READING, REQ_READING);
        if (!masterOn(context)
                || !prefs(context).getBoolean(KEY_READING_ENABLED, false)
                || !prefs(context).getBoolean(KEY_SYSTEM, true)) {
            am.cancel(pi);
            return;
        }
        long at = nextClockMillis(prefs(context).getString(KEY_READING_TIME, "21:00"));
        setWakeup(context, am, at, pi, REQ_READING_SHOW, true);
        Log.i(TAG, "reading alarm " + formatAt(at));
    }

    private static void scheduleTodos(Context context) {
        AlarmManager am = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        if (am == null) {
            return;
        }
        JSONArray todos;
        try {
            todos = new JSONArray(prefs(context).getString(KEY_TODOS_JSON, "[]"));
        } catch (Exception e) {
            return;
        }
        if (!masterOn(context) || !prefs(context).getBoolean(KEY_SYSTEM, true)) {
            return;
        }
        for (int i = 0; i < todos.length(); i++) {
            JSONObject todo = todos.optJSONObject(i);
            if (todo == null) {
                continue;
            }
            int id = todo.optInt("id", 0);
            if (id <= 0 || todo.optBoolean("completed", false)) {
                continue;
            }
            String text = todo.optString("text", "");
            long at = nextTodoMillis(todo.optString("date", ""), todo.optString("time", ""));
            if (at <= 0) {
                continue;
            }
            setWakeup(
                    context,
                    am,
                    at,
                    pendingTodo(context, id, text),
                    TODO_SHOW_BASE + id,
                    true
            );
            Log.i(TAG, "todo " + id + " alarm " + formatAt(at));
        }
    }

    private static void cancelTodoAlarms(Context context) {
        AlarmManager am = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        if (am == null) {
            return;
        }
        try {
            JSONArray todos = new JSONArray(prefs(context).getString(KEY_TODOS_JSON, "[]"));
            for (int i = 0; i < todos.length(); i++) {
                JSONObject todo = todos.optJSONObject(i);
                if (todo == null) {
                    continue;
                }
                int id = todo.optInt("id", 0);
                if (id > 0) {
                    am.cancel(pendingTodo(context, id, ""));
                }
            }
        } catch (Exception ignored) {
        }
    }

    private static void cancelAll(Context context) {
        AlarmManager am = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        if (am == null) {
            return;
        }
        am.cancel(pending(context, ACTION_DAILY, REQ_DAILY));
        am.cancel(pending(context, ACTION_POLL, REQ_POLL));
        am.cancel(pending(context, ACTION_READING, REQ_READING));
        am.cancel(pending(context, ACTION_TEST, REQ_TEST));
        cancelTodoAlarms(context);
    }

    private static void setWakeup(
            Context context,
            AlarmManager am,
            long at,
            PendingIntent pi,
            int showRequestCode,
            boolean userVisible
    ) {
        if (at <= 0) {
            return;
        }
        if (userVisible) {
            try {
                AlarmManager.AlarmClockInfo info = new AlarmManager.AlarmClockInfo(
                        at,
                        showActivity(context, showRequestCode)
                );
                am.setAlarmClock(info, pi);
                Log.i(TAG, "setAlarmClock at " + formatAt(at));
                return;
            } catch (SecurityException e) {
                Log.w(TAG, "setAlarmClock denied, falling back", e);
            } catch (Exception e) {
                Log.w(TAG, "setAlarmClock failed, falling back", e);
            }
        }
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && !am.canScheduleExactAlarms()) {
                am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pi);
                Log.w(TAG, "inexact alarm at " + formatAt(at));
                return;
            }
            am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pi);
            Log.i(TAG, "setExactAndAllowWhileIdle at " + formatAt(at));
        } catch (SecurityException e) {
            Log.w(TAG, "exact alarm denied, using inexact", e);
            am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pi);
        }
    }

    private static PendingIntent showActivity(Context context, int requestCode) {
        Intent show = new Intent(context, MainActivity.class);
        show.setAction(Intent.ACTION_MAIN);
        show.addCategory(Intent.CATEGORY_LAUNCHER);
        show.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            flags |= PendingIntent.FLAG_IMMUTABLE;
        }
        return PendingIntent.getActivity(context, requestCode, show, flags);
    }

    private static PendingIntent pending(Context context, String action, int requestCode) {
        Intent intent = new Intent(context, ReminderAlarmReceiver.class);
        intent.setAction(action);
        intent.addFlags(Intent.FLAG_RECEIVER_FOREGROUND);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            flags |= PendingIntent.FLAG_IMMUTABLE;
        }
        return PendingIntent.getBroadcast(context, requestCode, intent, flags);
    }

    private static PendingIntent pendingTodo(Context context, int todoId, String text) {
        Intent intent = new Intent(context, ReminderAlarmReceiver.class);
        intent.setAction(ACTION_TODO);
        intent.addFlags(Intent.FLAG_RECEIVER_FOREGROUND);
        intent.putExtra(EXTRA_TODO_ID, todoId);
        intent.putExtra(EXTRA_TODO_TEXT, text == null ? "" : text);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            flags |= PendingIntent.FLAG_IMMUTABLE;
        }
        return PendingIntent.getBroadcast(context, TODO_REQ_BASE + todoId, intent, flags);
    }

    private static long nextClockMillis(String rawTime) {
        int[] hm = parseTime(rawTime);
        Calendar cal = Calendar.getInstance();
        cal.set(Calendar.SECOND, 0);
        cal.set(Calendar.MILLISECOND, 0);
        cal.set(Calendar.HOUR_OF_DAY, hm[0]);
        cal.set(Calendar.MINUTE, hm[1]);
        if (cal.getTimeInMillis() <= System.currentTimeMillis() + 3000) {
            cal.add(Calendar.DAY_OF_MONTH, 1);
        }
        return cal.getTimeInMillis();
    }

    private static long nextTodoMillis(String dateRaw, String timeRaw) {
        int[] hm = parseTime(timeRaw);
        Calendar cal = Calendar.getInstance();
        cal.set(Calendar.SECOND, 0);
        cal.set(Calendar.MILLISECOND, 0);
        if (dateRaw != null && dateRaw.length() >= 10) {
            try {
                String[] parts = dateRaw.substring(0, 10).split("-");
                cal.set(Calendar.YEAR, Integer.parseInt(parts[0]));
                cal.set(Calendar.MONTH, Integer.parseInt(parts[1]) - 1);
                cal.set(Calendar.DAY_OF_MONTH, Integer.parseInt(parts[2]));
            } catch (Exception ignored) {
            }
        }
        cal.set(Calendar.HOUR_OF_DAY, hm[0]);
        cal.set(Calendar.MINUTE, hm[1]);
        if (cal.getTimeInMillis() <= System.currentTimeMillis() + 3000) {
            return -1;
        }
        return cal.getTimeInMillis();
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

    private static String formatAt(long at) {
        return new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(new Date(at));
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

    private static boolean hasStoredTodos(SharedPreferences p) {
        String raw = p.getString(KEY_TODOS_JSON, "");
        return raw != null && raw.length() > 2;
    }
}
