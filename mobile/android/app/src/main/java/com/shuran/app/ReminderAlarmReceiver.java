package com.shuran.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.PowerManager;
import android.util.Log;

public class ReminderAlarmReceiver extends BroadcastReceiver {
    private static final String TAG = "ShuranReminder";
    private static final long WAKE_MS = 60_000L;

    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null) {
            return;
        }
        final Context app = context.getApplicationContext();
        final Intent copy = intent == null ? null : new Intent(intent);

        PowerManager pm = (PowerManager) app.getSystemService(Context.POWER_SERVICE);
        final PowerManager.WakeLock lock = pm == null ? null : pm.newWakeLock(
                PowerManager.PARTIAL_WAKE_LOCK,
                "shuran:reminder"
        );
        if (lock != null) {
            lock.setReferenceCounted(false);
            try {
                lock.acquire(WAKE_MS);
            } catch (Exception e) {
                Log.w(TAG, "wake lock failed", e);
            }
        }

        // 到点先在 Receiver 主线程弹出通知，不等网络、不等登录、不另开线程。
        ReminderScheduler.Delivery delivery = ReminderScheduler.deliverLocal(app, copy);

        boolean startedService = false;
        if (delivery.userVisible) {
            try {
                Intent svc = new Intent(app, ReminderDeliveryService.class);
                if (copy != null) {
                    svc.setAction(copy.getAction());
                    if (copy.getExtras() != null) {
                        svc.putExtras(copy);
                    }
                }
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    app.startForegroundService(svc);
                } else {
                    app.startService(svc);
                }
                startedService = true;
            } catch (Exception e) {
                Log.w(TAG, "delivery service start failed", e);
            }
        }

        if (startedService) {
            release(lock);
            return;
        }

        if (!delivery.poll) {
            release(lock);
            return;
        }

        final PendingResult result = goAsync();
        new Thread(() -> {
            try {
                ReminderScheduler.pollNowBlocking(app);
            } catch (Exception e) {
                Log.e(TAG, "alarm poll failed", e);
            } finally {
                try {
                    result.finish();
                } catch (Exception ignored) {
                }
                release(lock);
            }
        }, "shuran-reminder-poll").start();
    }

    private static void release(PowerManager.WakeLock lock) {
        if (lock != null && lock.isHeld()) {
            try {
                lock.release();
            } catch (Exception ignored) {
            }
        }
    }
}
