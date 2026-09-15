package com.shuran.app;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.os.Handler;
import android.os.Looper;
import android.view.KeyEvent;
import android.view.accessibility.AccessibilityEvent;

/**
 * 锁屏或其它应用上监听音量减三连击，唤起「记」。
 * App 在前台时由 {@link MainActivity} 直接处理，不依赖本服务。
 */
public class TimeLogVolumeKeyService extends AccessibilityService {
    private final Handler handler = new Handler(Looper.getMainLooper());
    private VolumeTripleTapController controller;

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        /* 只要按键，不读界面 */
    }

    @Override
    public void onInterrupt() {
        if (controller != null) {
            controller.cancel();
        }
    }

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        controller = new VolumeTripleTapController(this, handler);
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
        return controller != null && controller.onKeyEvent(event);
    }

    @Override
    public void onDestroy() {
        if (controller != null) {
            controller.cancel();
        }
        super.onDestroy();
    }
}
