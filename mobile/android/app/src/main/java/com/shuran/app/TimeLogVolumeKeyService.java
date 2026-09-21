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
        // AccessibilityService can be rebound after its hosting process is reclaimed.
        // Always create a fresh controller so the detector does not retain stale state.
        if (controller != null) {
            controller.cancel();
        }
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
        if (controller == null) {
            controller = new VolumeTripleTapController(this, handler);
        }
        return controller.onKeyEvent(event);
    }

    @Override
    public boolean onUnbind(android.content.Intent intent) {
        // Ask Android to call onRebind if the service is attached again instead of
        // treating the accessibility connection as permanently gone.
        if (controller != null) {
            controller.cancel();
        }
        return true;
    }

    @Override
    public void onRebind(android.content.Intent intent) {
        super.onRebind(intent);
        if (controller == null) {
            controller = new VolumeTripleTapController(this, handler);
        }
    }

    @Override
    public void onDestroy() {
        if (controller != null) {
            controller.cancel();
        }
        super.onDestroy();
    }
}
