package com.shuran.app;

final class CaptureKinds {
    static final String MOMENT = "moment";
    static final String IDEA = "idea";
    static final String TODO = "todo";
    static final String TODAY = "today";
    static final String LATER = "later";
    static final String PREF_KIND = "capture_kind";

    private CaptureKinds() {}

    static String normalizeKind(String kind) {
        if (IDEA.equals(kind) || TODO.equals(kind) || MOMENT.equals(kind)) {
            return kind;
        }
        return MOMENT;
    }

    static String normalizeWhen(String when) {
        if (LATER.equals(when) || TODAY.equals(when)) {
            return when;
        }
        return TODAY;
    }
}
