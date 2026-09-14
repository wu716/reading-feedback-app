package com.shuran.app;

import android.annotation.SuppressLint;
import android.content.Intent;
import android.os.Build;
import android.service.quicksettings.TileService;

@SuppressLint("Override")
public class TimeLogTileService extends TileService {
    @Override
    public void onClick() {
        Intent intent = TimeLogAssist.punchIntent(this);
        if (Build.VERSION.SDK_INT >= 24) {
            startActivityAndCollapse(intent);
        } else {
            startActivity(intent);
        }
    }
}
