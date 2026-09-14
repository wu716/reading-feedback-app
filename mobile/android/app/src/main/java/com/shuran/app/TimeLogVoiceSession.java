package com.shuran.app;

import android.content.Context;
import android.os.Bundle;
import android.service.voice.VoiceInteractionSession;

public class TimeLogVoiceSession extends VoiceInteractionSession {
    public TimeLogVoiceSession(Context context) {
        super(context);
    }

    @Override
    public void onShow(Bundle args, int showFlags) {
        super.onShow(args, showFlags);
        TimeLogAssist.launchPunch(getContext());
        hide();
        finish();
    }
}
