package com.shuran.app;

import org.junit.Before;
import org.junit.Test;

import static com.shuran.app.VolumeTripleTap.ACTION_DOWN;
import static com.shuran.app.VolumeTripleTap.ACTION_UP;
import static com.shuran.app.VolumeTripleTap.COOLDOWN_MS;
import static com.shuran.app.VolumeTripleTap.GAP_MS;
import static com.shuran.app.VolumeTripleTap.KEYCODE_VOLUME_DOWN;
import static com.shuran.app.VolumeTripleTap.Result;
import static org.junit.Assert.assertEquals;

public class VolumeTripleTapTest {
    private static final int KEYCODE_VOLUME_UP = 24;
    private VolumeTripleTap tap;

    @Before
    public void setUp() {
        tap = new VolumeTripleTap();
    }

    @Test
    public void singleTapPassesThrough() {
        assertEquals(Result.PASS, tap.onKey(KEYCODE_VOLUME_DOWN, ACTION_DOWN, 0L, 0));
        assertEquals(Result.PASS, tap.onKey(KEYCODE_VOLUME_DOWN, ACTION_UP, 40L, 0));
    }

    @Test
    public void volumeUpIsIgnored() {
        assertEquals(Result.PASS, tap.onKey(KEYCODE_VOLUME_UP, ACTION_DOWN, 0L, 0));
        assertEquals(Result.PASS, tap.onKey(KEYCODE_VOLUME_DOWN, ACTION_DOWN, 100L, 0));
        assertEquals(Result.PASS, tap.onKey(KEYCODE_VOLUME_UP, ACTION_DOWN, 200L, 0));
    }

    @Test
    public void threeTapsWithinGapTrigger() {
        assertEquals(Result.PASS, down(0L));
        up(30L);
        assertEquals(Result.DEFER, down(400L));
        assertEquals(Result.CONSUME, up(430L));
        assertEquals(Result.TRIGGER, down(800L));
        assertEquals(Result.CONSUME, up(830L));
    }

    @Test
    public void slowTapsDoNotTrigger() {
        assertEquals(Result.PASS, down(0L));
        up(30L);
        assertEquals(Result.PASS, down(GAP_MS + 1));
        up(GAP_MS + 40);
        assertEquals(Result.DEFER, down(GAP_MS + 400));
        assertEquals(Result.CONSUME, up(GAP_MS + 430));
    }

    @Test
    public void twoTapsAreNotEnough() {
        assertEquals(Result.PASS, down(0L));
        up(20L);
        assertEquals(Result.DEFER, down(300L));
        assertEquals(Result.CONSUME, up(330L));
    }

    @Test
    public void longPressResetsAndPasses() {
        assertEquals(Result.PASS, down(0L));
        assertEquals(Result.PASS, tap.onKey(KEYCODE_VOLUME_DOWN, ACTION_DOWN, 80L, 1));
        assertEquals(Result.PASS, down(200L));
    }

    @Test
    public void cooldownConsumesRepeatTrigger() {
        down(0L);
        up(20L);
        down(300L);
        up(330L);
        assertEquals(Result.TRIGGER, down(600L));
        up(630L);
        down(700L);
        up(730L);
        down(1000L);
        up(1030L);
        assertEquals(Result.CONSUME, down(1100L));
    }

    @Test
    public void triggerWorksAgainAfterCooldown() {
        down(0L);
        up(20L);
        down(300L);
        up(330L);
        assertEquals(Result.TRIGGER, down(600L));
        up(630L);

        long later = 600L + COOLDOWN_MS + 50L;
        assertEquals(Result.PASS, down(later));
        up(later + 20L);
        assertEquals(Result.DEFER, down(later + 300L));
        up(later + 330L);
        assertEquals(Result.TRIGGER, down(later + 600L));
    }

    private Result down(long at) {
        return tap.onKey(KEYCODE_VOLUME_DOWN, ACTION_DOWN, at, 0);
    }

    private Result up(long at) {
        return tap.onKey(KEYCODE_VOLUME_DOWN, ACTION_UP, at, 0);
    }
}
