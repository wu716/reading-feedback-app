package com.shuran.app;

import android.app.Application;

public class ShuranApp extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        ReminderNotifications.ensureChannel(this);
        ReminderScheduler.restore(this);
    }
}
