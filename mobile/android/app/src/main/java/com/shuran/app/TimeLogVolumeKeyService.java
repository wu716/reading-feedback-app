package com.shuran.app;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.os.Build;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.view.KeyEvent;
import android.view.accessibility.AccessibilityEvent;

/**
 * 只监听音量减三连击，唤起「记」。不读屏幕、不抢单击调音量、不碰电源键。
 */
public class TimeLogVolumeKeyService extends AccessibilityService {
    private static final long WINDOW_MS = 800L;
    private static final long COOLDOWN_MS = 1200L;
    private static final int NEEDED = 3;

    private int downCount;
    private long firstDownAt;
    private boolean eatMatchingUp;
    private long lastPunchAt;

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        /* 只要按键，不读界面 */
    }

    @Override
    public void onInterrupt() {
        resetTaps();
    }

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        AccessibilityServiceInfo info = getServiceInfo();
        if (info != null) {
            info.flags |= AccessibilityServiceInfo.FLAG_REQUEST_FILTER_KEY_EVENTS;
            info.eventTypes = AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED;
            info.feedbackType = AccessibilityServiceInfo.FEEDBACK_GENERIC;
            setServiceInfo(info);
        }
    }

    @Override
    protected boolean onKeyEvent(KeyEvent event) {
        if (event == null || event.getKeyCode() != KeyEvent.KEYCODE_VOLUME_DOWN) {
            return false;
        }
        if (event.getAction() == KeyEvent.ACTION_UP && eatMatchingUp) {
            eatMatchingUp = false;
            return true;
        }
        if (event.getAction() != KeyEvent.ACTION_DOWN || event.getRepeatCount() > 0) {
            return false;
        }

        long now = event.getEventTime();
        if (downCount > 0 && now - firstDownAt > WINDOW_MS) {
            resetTaps();
        }
        if (downCount == 0) {
            firstDownAt = now;
        }
        downCount++;

        if (downCount < NEEDED) {
            return false;
        }
        resetTaps();
        if (now - lastPunchAt < COOLDOWN_MS) {
            eatMatchingUp = true;
            return true;
        }
        lastPunchAt = now;
        eatMatchingUp = true;
        buzz();
        TimeLogAssist.launchPunch(this);
        return true;
    }

    private void resetTaps() {
        downCount = 0;
        firstDownAt = 0;
    }

    private void buzz() {
        try {
            Vibrator vibrator = (Vibrator) getSystemService(VIBRATOR_SERVICE);
            if (vibrator == null || !vibrator.hasVibrator()) {
                return;
            }
            if (Build.VERSION.SDK_INT >= 26) {
                vibrator.vibrate(VibrationEffect.createOneShot(36, VibrationEffect.DEFAULT_AMPLITUDE));
            } else {
                vibrator.vibrate(36);
            }
        } catch (Exception ignored) {
        }
    }
}
