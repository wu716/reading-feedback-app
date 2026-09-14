package com.shuran.app;

import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Window;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

public class TimeLogPunchActivity extends Activity {
    private final Handler main = new Handler(Looper.getMainLooper());
    private TextView hintView;
    private EditText labelInput;
    private String pendingLoggedAt;
    private int pendingDuration;
    private boolean saving;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        super.onCreate(savedInstanceState);
        if (android.os.Build.VERSION.SDK_INT >= 27) {
            setShowWhenLocked(true);
            setTurnScreenOn(true);
        } else {
            getWindow().addFlags(
                    android.view.WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED
                            | android.view.WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON
            );
        }
        setContentView(R.layout.activity_time_log_punch);
        setFinishOnTouchOutside(true);
        hintView = findViewById(R.id.timelog_punch_hint);
        labelInput = findViewById(R.id.timelog_punch_input);
        Button later = findViewById(R.id.timelog_punch_later);
        Button save = findViewById(R.id.timelog_punch_save);
        later.setOnClickListener(v -> finish());
        save.setOnClickListener(v -> saveLabel());
        pendingLoggedAt = TimeLogClient.nowIso();
        hintView.setText(R.string.timelog_overlay_preparing);
        if (ReminderScheduler.sessionToken(this).isEmpty()) {
            toast(getString(R.string.timelog_need_login));
            finish();
            return;
        }
        final long clickedAt = System.currentTimeMillis();
        new Thread(() -> {
            try {
                JSONObject day = TimeLogClient.dayLog(this);
                int duration = TimeLogClient.durationSinceLast(day, clickedAt);
                main.post(() -> {
                    pendingDuration = duration;
                    hintView.setText(duration <= 0
                            ? getString(R.string.timelog_overlay_start)
                            : getString(R.string.timelog_overlay_elapsed, formatDuration(duration)));
                    labelInput.requestFocus();
                });
            } catch (Exception e) {
                main.post(() -> {
                    hintView.setText(R.string.timelog_overlay_start);
                    labelInput.requestFocus();
                });
            }
        }, "timelog-preview").start();
    }

    private void saveLabel() {
        if (saving) {
            return;
        }
        final String label = labelInput.getText() == null ? "" : labelInput.getText().toString().trim();
        if (label.isEmpty()) {
            finish();
            return;
        }
        saving = true;
        hintView.setText(R.string.timelog_overlay_saving);
        new Thread(() -> {
            try {
                TimeLogClient.punch(this, label, pendingLoggedAt);
                main.post(() -> {
                    toast(getString(R.string.timelog_overlay_saved));
                    finish();
                });
            } catch (Exception e) {
                main.post(() -> {
                    saving = false;
                    hintView.setText(pendingDuration <= 0
                            ? getString(R.string.timelog_overlay_start)
                            : getString(R.string.timelog_overlay_elapsed, formatDuration(pendingDuration)));
                    toast(e.getMessage() == null
                            ? getString(R.string.timelog_overlay_failed)
                            : e.getMessage());
                });
            }
        }, "timelog-save").start();
    }

    private void toast(String message) {
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show();
    }

    private String formatDuration(int seconds) {
        if (seconds < 60) {
            return seconds + " 秒";
        }
        int minutes = seconds / 60;
        int remain = seconds % 60;
        if (minutes < 60) {
            return remain == 0 ? minutes + " 分钟" : minutes + " 分 " + remain + " 秒";
        }
        int hours = minutes / 60;
        int rm = minutes % 60;
        return rm == 0 ? hours + " 小时" : hours + " 小时 " + rm + " 分";
    }
}
