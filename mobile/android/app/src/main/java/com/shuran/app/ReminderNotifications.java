package com.shuran.app;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;

import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;
import androidx.core.content.ContextCompat;

public final class ReminderNotifications {
    public static final String CHANNEL_ID = "shuran_system_reminders";
    public static final String EXTRA_OPEN_PATH = "open_path";
    public static final int DAILY_NOTIFICATION_ID = 9001;
    public static final int TEST_NOTIFICATION_ID = 9002;
    public static final int READING_NOTIFICATION_ID = 9003;

    private ReminderNotifications() {}

    public static void ensureChannel(Context context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return;
        }
        NotificationManager manager = context.getSystemService(NotificationManager.class);
        if (manager == null) {
            return;
        }
        NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                context.getString(R.string.notification_channel_name),
                NotificationManager.IMPORTANCE_HIGH
        );
        channel.setDescription(context.getString(R.string.notification_channel_desc));
        channel.enableVibration(true);
        channel.enableLights(true);
        channel.setShowBadge(true);
        channel.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
        manager.createNotificationChannel(channel);
    }

    public static boolean areEnabled(Context context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS)
                    != PackageManager.PERMISSION_GRANTED) {
                return false;
            }
        }
        return NotificationManagerCompat.from(context).areNotificationsEnabled();
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
                notificationId,
                open,
                flags
        );

        Notification notification = new NotificationCompat.Builder(context, CHANNEL_ID)
                .setSmallIcon(R.drawable.ic_stat_notify)
                .setContentTitle(safeTitle)
                .setContentText(safeBody)
                .setStyle(new NotificationCompat.BigTextStyle().bigText(safeBody))
                .setAutoCancel(true)
                .setCategory(NotificationCompat.CATEGORY_REMINDER)
                .setPriority(NotificationCompat.PRIORITY_MAX)
                .setDefaults(NotificationCompat.DEFAULT_ALL)
                .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                .setColor(ContextCompat.getColor(context, R.color.primary))
                .setContentIntent(contentIntent)
                .setTicker(safeTitle)
                .build();

        try {
            NotificationManagerCompat.from(context).notify(notificationId, notification);
        } catch (SecurityException ignored) {
            // Android 13+ 未授予 POST_NOTIFICATIONS 时系统会拒绝，由调用方提示用户
        }
    }
}
