package com.shuran.app;

import android.app.Service;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;
import android.util.Log;

/**
 * 闹钟到点后用短前台服务保住进程，再单独 notify 用户通知。
 * 占位通知和用户通知必须不同 id / 不同渠道，停服务时不能把用户通知撤掉。
 */
public class ReminderDeliveryService extends Service {
    private static final String TAG = "ShuranReminder";
    private static final long WAKE_MS = 60_000L;
    private static final long KEEP_ALIVE_MS = 4_000L;

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

        try {
            startForeground(
                    ReminderNotifications.DELIVERY_NOTIFICATION_ID,
                    ReminderNotifications.buildSilent(this)
            );
        } catch (Exception e) {
            Log.e(TAG, "startForeground failed", e);
        }

        ReminderScheduler.Delivery delivery;
        try {
            delivery = ReminderScheduler.deliverLocal(this, intent);
        } catch (Exception e) {
            Log.e(TAG, "delivery deliverLocal failed", e);
            delivery = new ReminderScheduler.Delivery();
        }

        final boolean poll = delivery.poll;
        new Thread(() -> {
            try {
                if (poll) {
                    ReminderScheduler.pollNowBlocking(this);
                }
                try {
                    Thread.sleep(KEEP_ALIVE_MS);
                } catch (InterruptedException ignored) {
                    Thread.currentThread().interrupt();
                }
            } catch (Exception e) {
                Log.e(TAG, "delivery poll failed", e);
            } finally {
                try {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                        stopForeground(STOP_FOREGROUND_REMOVE);
                    } else {
                        stopForeground(true);
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
