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
        final Intent copy = new Intent(intent);
        final String action = copy.getAction();
        Log.i(TAG, "alarm received action=" + action);

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

        // 轮询不走前台服务，避免无意义的状态栏占位。
        if (ReminderScheduler.ACTION_POLL.equals(action)) {
            ReminderScheduler.deliverLocal(app, copy);
            final PendingResult result = goAsync();
            new Thread(() -> {
                try {
                    ReminderScheduler.pollNowBlocking(app);
                } catch (Exception e) {
                    Log.e(TAG, "alarm poll failed", e);
                } finally {
                    finishQuiet(result);
                    release(lock);
                }
            }, "shuran-reminder-poll").start();
            return;
        }

        // 用户可见闹钟：先拉起短前台服务再投递。国产 ROM 常丢掉纯 Receiver 的 notify。
        boolean startedService = false;
        try {
            Intent svc = new Intent(app, ReminderDeliveryService.class);
            svc.setAction(action);
            if (copy.getExtras() != null) {
                svc.putExtras(copy);
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

        if (startedService) {
            release(lock);
            return;
        }

        // 服务拉不起时，Receiver 自己弹，并保持进程到投递结束。
        final PendingResult result = goAsync();
        try {
            ReminderScheduler.deliverLocal(app, copy);
        } catch (Exception e) {
            Log.e(TAG, "receiver deliver failed", e);
        }
        new Thread(() -> {
            try {
                ReminderScheduler.pollNowBlocking(app);
            } catch (Exception e) {
                Log.e(TAG, "alarm poll failed", e);
            } finally {
                finishQuiet(result);
                release(lock);
            }
        }, "shuran-reminder-fallback").start();
    }

    private static void finishQuiet(PendingResult result) {
        try {
            result.finish();
        } catch (Exception ignored) {
        }
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
