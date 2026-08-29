package com.shuran.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
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
        final String action = intent.getAction();
        final Intent copy = intent;
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
        final PendingResult result = goAsync();
        new Thread(() -> {
            try {
                if (ReminderScheduler.ACTION_DAILY.equals(action)) {
                    ReminderScheduler.onDailyAlarm(app);
                } else if (ReminderScheduler.ACTION_POLL.equals(action)) {
                    ReminderScheduler.onPollAlarm(app);
                } else if (ReminderScheduler.ACTION_READING.equals(action)) {
                    ReminderScheduler.onReadingAlarm(app);
                } else if (ReminderScheduler.ACTION_TODO.equals(action)) {
                    ReminderScheduler.onTodoAlarm(app, copy);
                } else if (ReminderScheduler.ACTION_TEST.equals(action)) {
                    ReminderScheduler.onTestAlarm(app);
                }
            } catch (Exception e) {
                Log.e(TAG, "alarm dispatch failed", e);
            } finally {
                try {
                    result.finish();
                } catch (Exception ignored) {
                }
                if (lock != null && lock.isHeld()) {
                    try {
                        lock.release();
                    } catch (Exception ignored) {
                    }
                }
            }
        }, "shuran-reminder-alarm").start();
    }
}
