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
    private CaptureKindBar kindBar;
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
        kindBar = findViewById(R.id.capture_kind_bar);
        Button later = findViewById(R.id.timelog_punch_later);
        Button save = findViewById(R.id.timelog_punch_save);
        later.setOnClickListener(v -> finish());
        save.setOnClickListener(v -> saveLabel());
        pendingLoggedAt = TimeLogClient.nowIso();
        if (kindBar != null) {
            kindBar.setKind(TimeLogClient.preferenceKind(this));
            kindBar.setListener((kind, todoWhen) -> paintHint());
        }
        hintView.setText(R.string.timelog_overlay_preparing);
        paintHint();
        if (ReminderScheduler.sessionToken(this).isEmpty()) {
            toast(getString(R.string.timelog_need_login));
            finish();
            return;
        }
        final long clickedAt = System.currentTimeMillis();
        new Thread(() -> {
            String kind = TimeLogClient.preferenceKind(this);
            try {
                kind = TimeLogClient.fetchPreferenceKind(this);
            } catch (Exception ignored) {
            }
            int duration = 0;
            try {
                JSONObject day = TimeLogClient.dayLog(this);
                duration = TimeLogClient.durationSinceLast(day, clickedAt);
            } catch (Exception ignored) {
            }
            final String resolvedKind = kind;
            final int resolvedDuration = duration;
            main.post(() -> {
                pendingDuration = resolvedDuration;
                if (kindBar != null) {
                    kindBar.setKind(resolvedKind);
                }
                paintHint();
                labelInput.requestFocus();
            });
        }, "timelog-preview").start();
    }

    private void paintHint() {
        String kind = kindBar == null ? CaptureKinds.MOMENT : kindBar.kind();
        if (CaptureKinds.IDEA.equals(kind)) {
            hintView.setText(R.string.capture_hint_idea);
            labelInput.setHint(R.string.capture_placeholder_idea);
            return;
        }
        if (CaptureKinds.TODO.equals(kind)) {
            hintView.setText(R.string.capture_hint_todo);
            labelInput.setHint(R.string.capture_placeholder_todo);
            return;
        }
        labelInput.setHint(R.string.timelog_overlay_hint);
        hintView.setText(pendingDuration <= 0
                ? getString(R.string.timelog_overlay_start)
                : getString(R.string.timelog_overlay_elapsed, formatDuration(pendingDuration)));
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
        final String kind = kindBar == null ? CaptureKinds.MOMENT : kindBar.kind();
        final String todoWhen = kindBar == null ? CaptureKinds.TODAY : kindBar.todoWhen();
        final String loggedAt = pendingLoggedAt;
        new Thread(() -> {
            try {
                TimeLogClient.capture(this, kind, label, todoWhen, loggedAt);
                main.post(() -> {
                    toast(savedMessage(kind, todoWhen));
                    finish();
                });
            } catch (Exception e) {
                main.post(() -> {
                    saving = false;
                    paintHint();
                    toast(e.getMessage() == null
                            ? getString(R.string.timelog_overlay_failed)
                            : e.getMessage());
                });
            }
        }, "timelog-save").start();
    }

    private String savedMessage(String kind, String todoWhen) {
        if (CaptureKinds.IDEA.equals(kind)) {
            return getString(R.string.capture_saved_idea);
        }
        if (CaptureKinds.TODO.equals(kind)) {
            return CaptureKinds.LATER.equals(todoWhen)
                    ? getString(R.string.capture_saved_todo_later)
                    : getString(R.string.capture_saved_todo_today);
        }
        return getString(R.string.capture_saved_moment);
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
