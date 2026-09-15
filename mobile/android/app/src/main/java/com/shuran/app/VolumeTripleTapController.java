package com.shuran.app;

import android.content.Context;
import android.media.AudioManager;
import android.os.Handler;
import android.view.KeyEvent;

/**
 * 把 {@link VolumeTripleTap} 接到按键事件：触发时打开「记」，
 * 未凑满三击时把暂扣的音量减补回去。
 */
final class VolumeTripleTapController {
    private final VolumeTripleTap detector = new VolumeTripleTap();
    private final Handler handler;
    private final Context appContext;
    private final Runnable applyDeferredVolume;
    private int deferredSteps;

    VolumeTripleTapController(Context context, Handler handler) {
        this.appContext = context.getApplicationContext();
        this.handler = handler;
        this.applyDeferredVolume = this::flushDeferredVolume;
    }

    boolean onKeyEvent(KeyEvent event) {
        if (event == null) {
            return false;
        }
        VolumeTripleTap.Result result = detector.onKey(
                event.getKeyCode(),
                event.getAction(),
                event.getEventTime(),
                event.getRepeatCount()
        );
        if (result == VolumeTripleTap.Result.PASS) {
            return false;
        }
        if (result == VolumeTripleTap.Result.DEFER) {
            deferredSteps++;
            handler.removeCallbacks(applyDeferredVolume);
            handler.postDelayed(applyDeferredVolume, VolumeTripleTap.GAP_MS);
            return true;
        }
        if (result == VolumeTripleTap.Result.TRIGGER) {
            handler.removeCallbacks(applyDeferredVolume);
            deferredSteps = 0;
            TimeLogAssist.buzz(appContext);
            TimeLogAssist.launchPunch(appContext);
            return true;
        }
        return true;
    }

    void cancel() {
        handler.removeCallbacks(applyDeferredVolume);
        deferredSteps = 0;
        detector.reset();
    }

    private void flushDeferredVolume() {
        detector.reset();
        int steps = deferredSteps;
        deferredSteps = 0;
        if (steps <= 0) {
            return;
        }
        AudioManager audio = (AudioManager) appContext.getSystemService(Context.AUDIO_SERVICE);
        if (audio == null) {
            return;
        }
        for (int i = 0; i < steps; i++) {
            audio.adjustVolume(AudioManager.ADJUST_LOWER, AudioManager.FLAG_SHOW_UI);
        }
    }
}
