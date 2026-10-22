package com.shuran.app;

import org.junit.Test;
import java.time.Instant;
import java.util.TimeZone;
import static org.junit.Assert.assertEquals;

public class ReminderCalendarTest {
    private static long at(String utc) { return Instant.parse(utc).toEpochMilli(); }

    @Test public void schedulesForBeijingEvenWhenDeviceTimezoneDiffers() {
        TimeZone previous = TimeZone.getDefault();
        try {
            TimeZone.setDefault(TimeZone.getTimeZone("America/Los_Angeles"));
            assertEquals(at("2026-10-22T13:00:00Z"), ReminderScheduler.nextRecordMillis(
                    "21:00", "", "", at("2026-10-22T12:00:00Z")));
        } finally { TimeZone.setDefault(previous); }
    }

    @Test public void openingAfterDueTimeStillRemindsToday() {
        long now = at("2026-10-22T14:00:00Z");
        assertEquals(now + 3000, ReminderScheduler.nextRecordMillis("21:00", "", "", now));
    }

    @Test public void completedDaySchedulesTomorrow() {
        assertEquals(at("2026-10-23T13:00:00Z"), ReminderScheduler.nextRecordMillis(
                "21:00", "2026-10-22", "", at("2026-10-22T12:00:00Z")));
    }

    @Test public void serverOrLocalDeliveryPreventsAnotherAlarmToday() {
        assertEquals(at("2026-10-23T13:00:00Z"), ReminderScheduler.nextRecordMillis(
                "21:00", "", "2026-10-22", at("2026-10-22T13:00:00Z")));
    }

    @Test public void yesterdayDoesNotSuppressTodayAtTheYearBoundary() {
        assertEquals(at("2027-01-01T13:00:00Z"), ReminderScheduler.nextRecordMillis(
                "21:00", "2026-12-31", "2026-12-31", at("2026-12-31T16:10:00Z")));
    }
}
