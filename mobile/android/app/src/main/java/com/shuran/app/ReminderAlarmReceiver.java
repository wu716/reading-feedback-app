package com.shuran.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public class ReminderAlarmReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null) {
            return;
        }
        final PendingResult result = goAsync();
        final String action = intent.getAction();
        new Thread(() -> {
            try {
                if (ReminderScheduler.ACTION_DAILY.equals(action)) {
                    ReminderScheduler.onDailyAlarm(context.getApplicationContext());
                } else if (ReminderScheduler.ACTION_POLL.equals(action)) {
                    ReminderScheduler.onPollAlarm(context.getApplicationContext());
                } else if (ReminderScheduler.ACTION_READING.equals(action)) {
                    ReminderScheduler.onReadingAlarm(context.getApplicationContext());
                } else if (ReminderScheduler.ACTION_TODO.equals(action)) {
                    ReminderScheduler.onTodoAlarm(context.getApplicationContext(), intent);
                }
            } finally {
                result.finish();
            }
        }, "shuran-reminder-alarm").start();
    }
}
