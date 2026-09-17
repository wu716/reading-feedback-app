package com.shuran.app;

import org.junit.Test;

import static org.junit.Assert.assertEquals;

public class CaptureKindsTest {
    @Test
    public void unknownKindFallsBackToMoment() {
        assertEquals(CaptureKinds.MOMENT, CaptureKinds.normalizeKind(null));
        assertEquals(CaptureKinds.MOMENT, CaptureKinds.normalizeKind("diary"));
    }

    @Test
    public void knownKindsPassThrough() {
        assertEquals(CaptureKinds.IDEA, CaptureKinds.normalizeKind("idea"));
        assertEquals(CaptureKinds.TODO, CaptureKinds.normalizeKind("todo"));
    }

    @Test
    public void todoWhenDefaultsToToday() {
        assertEquals(CaptureKinds.TODAY, CaptureKinds.normalizeWhen(null));
        assertEquals(CaptureKinds.LATER, CaptureKinds.normalizeWhen("later"));
    }
}
