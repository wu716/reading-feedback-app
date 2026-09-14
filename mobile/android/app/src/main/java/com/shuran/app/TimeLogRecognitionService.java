package com.shuran.app;

import android.content.Intent;
import android.speech.RecognitionService;

public class TimeLogRecognitionService extends RecognitionService {
    @Override
    protected void onStartListening(Intent recognizerIntent, Callback callback) {
        try {
            callback.error(android.speech.SpeechRecognizer.ERROR_CLIENT);
        } catch (Exception ignored) {
        }
        TimeLogAssist.launchPunch(this);
    }

    @Override
    protected void onCancel(Callback callback) {
        try {
            callback.endOfSpeech();
        } catch (Exception ignored) {
        }
    }

    @Override
    protected void onStopListening(Callback callback) {
        try {
            callback.endOfSpeech();
        } catch (Exception ignored) {
        }
    }
}
