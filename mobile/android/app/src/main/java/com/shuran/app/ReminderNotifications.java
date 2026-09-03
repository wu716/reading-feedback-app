package com.shuran.app;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.media.AudioAttributes;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;

import androidx.core.app.NotificationCompat;
import androidx.core.content.ContextCompat;

public final class ReminderNotifications {
    /** 新渠道：旧渠道 importance 一旦建成就改不了，必须换 id 才能 heads-up。 */
    public static final String CHANNEL_ID = "shuran_alarms_v2";
    public static final String LEGACY_CHANNEL_ID = "shuran_system_reminders";
    public static final String EXTRA_OPEN_PATH = "open_path";
    public static final int DAILY_NOTIFICATION_ID = 9001;
    public static final int TEST_NOTIFICATION_ID = 9002;
    public static final int READING_NOTIFICATION_ID = 9003;
    public static final int DELIVERY_NOTIFICATION_ID = 9000;

    private ReminderNotifications() {}

    public static void ensureChannel(Context context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return;
        }
        NotificationManager manager = context.getSystemService(NotificationManager.class);
        if (manager == null) {
            return;
        }
        NotificationChannel existing = manager.getNotificationChannel(CHANNEL_ID);
        if (existing == null) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID,
                    context.getString(R.string.notification_channel_name),
                    NotificationManager.IMPORTANCE_HIGH
            );
            channel.setDescription(context.getString(R.string.notification_channel_desc));
            channel.enableVibration(true);
            channel.setVibrationPattern(new long[]{0, 400, 200, 400});
            channel.enableLights(true);
            channel.setShowBadge(true);
            channel.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
            channel.setBypassDnd(true);
            Uri sound = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM);
            if (sound == null) {
                sound = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION);
            }
            AudioAttributes audio = new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build();
            if (sound != null) {
                channel.setSound(sound, audio);
            }
            manager.createNotificationChannel(channel);
        } else if (existing.getImportance() < NotificationManager.IMPORTANCE_DEFAULT) {
            // 用户若关掉渠道无法在代码里抬高；仍确保振动等字段存在。
            existing.enableVibration(true);
            manager.createNotificationChannel(existing);
        }
        try {
            manager.deleteNotificationChannel(LEGACY_CHANNEL_ID);
        } catch (Exception ignored) {
        }
    }

    public static boolean areEnabled(Context context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS)
                    != PackageManager.PERMISSION_GRANTED) {
                return false;
            }
        }
        NotificationManager manager = context.getSystemService(NotificationManager.class);
        if (manager == null) {
            return false;
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N && !manager.areNotificationsEnabled()) {
            return false;
        }
        return true;
    }

    public static String resolveUrl(Context context, String path) {
        if (path == null || path.isEmpty()) {
            return context.getString(R.string.app_url);
        }
        if (path.startsWith("http://") || path.startsWith("https://")) {
            return path;
        }
        String origin = ReminderScheduler.apiOrigin(context);
        if (!path.startsWith("/")) {
            path = "/" + path;
        }
        return origin + path;
    }

    public static void showTest(Context context) {
        show(
                context,
                TEST_NOTIFICATION_ID,
                context.getString(R.string.notification_test_title),
                context.getString(R.string.notification_test_body),
                "/static/index.html#user-center"
        );
    }

    public static void show(Context context, int notificationId, String title, String body, String actionPath) {
        if (!areEnabled(context)) {
            return;
        }
        showPrepared(context, notificationId, build(context, title, body, actionPath));
    }

    public static void showPrepared(Context context, int notificationId, Notification notification) {
        if (notification == null) {
            return;
        }
        ensureChannel(context);
        NotificationManager manager = context.getSystemService(NotificationManager.class);
        if (manager == null) {
            return;
        }
        try {
            manager.notify(notificationId, notification);
        } catch (SecurityException ignored) {
        }
    }

    public static Notification build(Context context, String title, String body, String actionPath) {
        ensureChannel(context);

        String safeTitle = title == null || title.trim().isEmpty()
                ? context.getString(R.string.notification_default_title)
                : title.trim();
        String safeBody = body == null ? "" : body.trim();
        String path = actionPath == null || actionPath.isEmpty()
                ? "/static/self_talk/index.html"
                : actionPath;

        Intent open = new Intent(context, MainActivity.class);
        open.setAction(Intent.ACTION_VIEW);
        open.putExtra(EXTRA_OPEN_PATH, path);
        open.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK
                | Intent.FLAG_ACTIVITY_CLEAR_TOP
                | Intent.FLAG_ACTIVITY_SINGLE_TOP);

        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            flags |= PendingIntent.FLAG_IMMUTABLE;
        }
        PendingIntent contentIntent = PendingIntent.getActivity(
                context,
                Math.abs(path.hashCode()),
                open,
                flags
        );

        Uri sound = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM);
        if (sound == null) {
            sound = Settings.System.DEFAULT_NOTIFICATION_URI;
        }

        NotificationCompat.Builder builder = new NotificationCompat.Builder(context, CHANNEL_ID)
                .setSmallIcon(R.drawable.ic_stat_notify)
                .setContentTitle(safeTitle)
                .setContentText(safeBody)
                .setStyle(new NotificationCompat.BigTextStyle().bigText(safeBody))
                .setAutoCancel(true)
                .setCategory(NotificationCompat.CATEGORY_ALARM)
                .setPriority(NotificationCompat.PRIORITY_MAX)
                .setDefaults(NotificationCompat.DEFAULT_ALL)
                .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                .setColor(ContextCompat.getColor(context, R.color.primary))
                .setContentIntent(contentIntent)
                .setFullScreenIntent(contentIntent, true)
                .setTicker(safeTitle)
                .setSound(sound)
                .setVibrate(new long[]{0, 400, 200, 400})
                .setOnlyAlertOnce(false);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            builder.setVisibility(NotificationCompat.VISIBILITY_PUBLIC);
        }
        return builder.build();
    }
}
