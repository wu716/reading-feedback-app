package com.shuran.app;

/**
 * 音量减三连击检测。纯状态机，不依赖 Android 运行时，便于单元测试。
 *
 * <p>第 1 击放行（正常调音量）；第 2 击先按住，等第 3 击；第 3 击触发「记」。
 * 相邻两次按下超过 {@link #GAP_MS} 则重新计数。
 */
public final class VolumeTripleTap {
    public static final int KEYCODE_VOLUME_DOWN = 25;
    public static final int ACTION_DOWN = 0;
    public static final int ACTION_UP = 1;

    public static final long GAP_MS = 800L;
    public static final long COOLDOWN_MS = 1200L;
    public static final int NEEDED = 3;

    public enum Result {
        PASS,
        DEFER,
        CONSUME,
        TRIGGER
    }

    private int downCount;
    private long lastDownAt;
    private boolean eatMatchingUp;
    private long lastPunchAt = Long.MIN_VALUE / 2;

    public Result onKey(int keyCode, int action, long eventTime, int repeatCount) {
        if (keyCode != KEYCODE_VOLUME_DOWN) {
            return Result.PASS;
        }
        if (action == ACTION_UP && eatMatchingUp) {
            eatMatchingUp = false;
            return Result.CONSUME;
        }
        if (action != ACTION_DOWN) {
            return Result.PASS;
        }
        if (repeatCount > 0) {
            reset();
            return Result.PASS;
        }

        if (downCount > 0 && eventTime - lastDownAt > GAP_MS) {
            downCount = 0;
        }
        lastDownAt = eventTime;
        downCount++;

        if (downCount == 1) {
            return Result.PASS;
        }

        eatMatchingUp = true;
        if (downCount < NEEDED) {
            return Result.DEFER;
        }

        downCount = 0;
        if (eventTime - lastPunchAt < COOLDOWN_MS) {
            return Result.CONSUME;
        }
        lastPunchAt = eventTime;
        return Result.TRIGGER;
    }

    public void reset() {
        downCount = 0;
        lastDownAt = 0;
        eatMatchingUp = false;
    }
}
