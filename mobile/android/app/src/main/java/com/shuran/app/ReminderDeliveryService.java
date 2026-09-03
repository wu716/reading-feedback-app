package com.shuran.app;

import android.app.Notification;
import android.app.Service;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;
import android.util.Log;

/**
 * AlarmManager 触发后用短前台服务投递通知。
 * 国产 ROM 上纯 BroadcastReceiver 后台 notify 经常被丢掉；FGS 通知一定会进通知栏。
 */
public class ReminderDeliveryService extends Service {
    private static final String TAG = "ShuranReminder";
    private static final long WAKE_MS = 60_000L;

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
        final PowerManager.WakeLock lock = pm == null ? null : pm.newWakeLock(
                PowerManager.PARTIAL_WAKE_LOCK,
                "shuran:delivery"
        );
        if (lock != null) {
            lock.setReferenceCounted(false);
            try {
                lock.acquire(WAKE_MS);
            } catch (Exception e) {
                Log.w(TAG, "delivery wake lock failed", e);
            }
        }

        ReminderScheduler.Delivery delivery = ReminderScheduler.deliverLocal(this, intent);
        Notification notification = delivery.notification;
        if (notification == null) {
            notification = ReminderNotifications.build(
                    this,
                    getString(R.string.notification_default_title),
                    getString(R.string.notification_daily_body),
                    "/static/index.html"
            );
        }
        int notifyId = delivery.notificationId != 0
                ? delivery.notificationId
                : ReminderNotifications.DELIVERY_NOTIFICATION_ID;
        try {
            startForeground(notifyId, notification);
        } catch (Exception e) {
            Log.e(TAG, "startForeground failed", e);
            ReminderNotifications.showPrepared(this, notifyId, notification);
        }

        final boolean poll = delivery.poll;
        new Thread(() -> {
            try {
                if (poll) {
                    ReminderScheduler.pollNowBlocking(this);
                }
            } catch (Exception e) {
                Log.e(TAG, "delivery poll failed", e);
            } finally {
                try {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                        stopForeground(STOP_FOREGROUND_DETACH);
                    } else {
                        stopForeground(false);
                    }
                } catch (Exception ignored) {
                }
                if (lock != null && lock.isHeld()) {
                    try {
                        lock.release();
                    } catch (Exception ignored) {
                    }
                }
                stopSelf(startId);
            }
        }, "shuran-reminder-delivery").start();
        return START_NOT_STICKY;
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
