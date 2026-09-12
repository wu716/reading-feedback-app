package com.shuran.app;

import android.app.Notification;
import android.app.Service;
import android.content.Intent;
import android.graphics.PixelFormat;
import android.graphics.Typeface;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import androidx.core.app.NotificationCompat;

import org.json.JSONObject;

public class TimeLogOverlayService extends Service {
    public static final int NOTIFICATION_ID = 9101;

    private final Handler main = new Handler(Looper.getMainLooper());
    private WindowManager windowManager;
    private View bubble;
    private View panel;
    private WindowManager.LayoutParams bubbleParams;
    private WindowManager.LayoutParams panelParams;
    private EditText labelInput;
    private TextView panelHint;
    private int pendingNodeId;
    private boolean punching;

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onCreate() {
        super.onCreate();
        startForeground(NOTIFICATION_ID, buildNotification());
        windowManager = (WindowManager) getSystemService(WINDOW_SERVICE);
        if (windowManager == null) {
            stopSelf();
            return;
        }
        createBubble();
        createPanel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (!TimeLogOverlay.hasPermission(this) || !TimeLogOverlay.isEnabled(this)) {
            stopSelf();
            return START_NOT_STICKY;
        }
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        removeView(bubble);
        removeView(panel);
        super.onDestroy();
    }

    private Notification buildNotification() {
        ReminderNotifications.ensureChannel(this);
        Intent open = new Intent(this, MainActivity.class);
        open.addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
        return new NotificationCompat.Builder(this, ReminderNotifications.DELIVERY_CHANNEL_ID)
                .setSmallIcon(R.mipmap.ic_launcher)
                .setContentTitle(getString(R.string.timelog_overlay_title))
                .setContentText(getString(R.string.timelog_overlay_body))
                .setOngoing(true)
                .setSilent(true)
                .setContentIntent(android.app.PendingIntent.getActivity(
                        this,
                        9101,
                        open,
                        Build.VERSION.SDK_INT >= 23
                                ? android.app.PendingIntent.FLAG_UPDATE_CURRENT | android.app.PendingIntent.FLAG_IMMUTABLE
                                : android.app.PendingIntent.FLAG_UPDATE_CURRENT
                ))
                .build();
    }

    private int overlayType() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            return WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY;
        }
        return WindowManager.LayoutParams.TYPE_PHONE;
    }

    private int dp(int value) {
        return Math.round(TypedValue.applyDimension(
                TypedValue.COMPLEX_UNIT_DIP, value, getResources().getDisplayMetrics()));
    }

    private void createBubble() {
        TextView button = new TextView(this);
        button.setText("记");
        button.setTextColor(0xFFF3EFE6);
        button.setTypeface(Typeface.SERIF);
        button.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16);
        button.setGravity(Gravity.CENTER);
        button.setBackgroundColor(0xFF1C1B19);
        int size = dp(48);
        bubble = button;
        bubbleParams = new WindowManager.LayoutParams(
                size,
                size,
                overlayType(),
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT
        );
        bubbleParams.gravity = Gravity.TOP | Gravity.START;
        bubbleParams.x = dp(12);
        bubbleParams.y = dp(180);
        attachDrag(button);
        button.setOnClickListener(v -> onPunch());
        windowManager.addView(bubble, bubbleParams);
    }

    private void createPanel() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(16), dp(16), dp(16), dp(16));
        box.setBackgroundColor(0xFFF3EFE6);

        panelHint = new TextView(this);
        panelHint.setTextColor(0xFF1C1B19);
        panelHint.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        panelHint.setTypeface(Typeface.SERIF);
        box.addView(panelHint);

        labelInput = new EditText(this);
        labelInput.setHint(R.string.timelog_overlay_hint);
        labelInput.setTextColor(0xFF1C1B19);
        labelInput.setHintTextColor(0xFF8A8478);
        LinearLayout.LayoutParams inputParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
        );
        inputParams.topMargin = dp(10);
        box.addView(labelInput, inputParams);

        LinearLayout actions = new LinearLayout(this);
        actions.setOrientation(LinearLayout.HORIZONTAL);
        actions.setGravity(Gravity.END);
        LinearLayout.LayoutParams actionsParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
        );
        actionsParams.topMargin = dp(10);

        Button later = new Button(this);
        later.setText(R.string.timelog_overlay_later);
        later.setOnClickListener(v -> hidePanel());
        actions.addView(later);

        Button save = new Button(this);
        save.setText(R.string.timelog_overlay_save);
        save.setOnClickListener(v -> saveLabel());
        actions.addView(save);
        box.addView(actions, actionsParams);

        panel = box;
        panel.setVisibility(View.GONE);
        panelParams = new WindowManager.LayoutParams(
                dp(300),
                WindowManager.LayoutParams.WRAP_CONTENT,
                overlayType(),
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT
        );
        panelParams.gravity = Gravity.TOP | Gravity.START;
        panelParams.x = dp(12);
        panelParams.y = dp(240);
        windowManager.addView(panel, panelParams);
    }

    private void attachDrag(View view) {
        view.setOnTouchListener(new View.OnTouchListener() {
            float downX;
            float downY;
            int startX;
            int startY;
            boolean dragging;

            @Override
            public boolean onTouch(View v, MotionEvent event) {
                switch (event.getActionMasked()) {
                    case MotionEvent.ACTION_DOWN:
                        downX = event.getRawX();
                        downY = event.getRawY();
                        startX = bubbleParams.x;
                        startY = bubbleParams.y;
                        dragging = false;
                        return true;
                    case MotionEvent.ACTION_MOVE:
                        int dx = Math.round(event.getRawX() - downX);
                        int dy = Math.round(event.getRawY() - downY);
                        if (Math.abs(dx) > dp(6) || Math.abs(dy) > dp(6)) {
                            dragging = true;
                        }
                        if (dragging) {
                            bubbleParams.x = Math.max(0, startX + dx);
                            bubbleParams.y = Math.max(0, startY + dy);
                            windowManager.updateViewLayout(bubble, bubbleParams);
                        }
                        return true;
                    case MotionEvent.ACTION_UP:
                        if (!dragging) {
                            v.performClick();
                        }
                        return true;
                    default:
                        return false;
                }
            }
        });
    }

    private void onPunch() {
        if (punching) {
            return;
        }
        if (ReminderScheduler.sessionToken(this).isEmpty()) {
            toast(getString(R.string.timelog_need_login));
            return;
        }
        punching = true;
        showPanel(getString(R.string.timelog_overlay_saving), "");
        new Thread(() -> {
            try {
                JSONObject node = TimeLogClient.punch(this, null);
                int id = node.optInt("id");
                int duration = node.optInt("duration_seconds");
                main.post(() -> {
                    pendingNodeId = id;
                    punching = false;
                    String hint = duration <= 0
                            ? getString(R.string.timelog_overlay_start)
                            : getString(R.string.timelog_overlay_elapsed, formatDuration(duration));
                    showPanel(hint, "");
                });
            } catch (Exception e) {
                main.post(() -> {
                    punching = false;
                    hidePanel();
                    toast(e.getMessage() == null ? getString(R.string.timelog_overlay_failed) : e.getMessage());
                });
            }
        }, "timelog-punch").start();
    }

    private void saveLabel() {
        if (pendingNodeId <= 0) {
            hidePanel();
            return;
        }
        final String label = labelInput.getText() == null ? "" : labelInput.getText().toString();
        final int nodeId = pendingNodeId;
        new Thread(() -> {
            try {
                TimeLogClient.updateLabel(this, nodeId, label);
                main.post(() -> {
                    hidePanel();
                    toast(getString(R.string.timelog_overlay_saved));
                });
            } catch (Exception e) {
                main.post(() -> toast(e.getMessage() == null
                        ? getString(R.string.timelog_overlay_failed)
                        : e.getMessage()));
            }
        }, "timelog-label").start();
    }

    private void showPanel(String hint, String label) {
        panelHint.setText(hint);
        labelInput.setText(label);
        panel.setVisibility(View.VISIBLE);
        panelParams.x = bubbleParams.x;
        panelParams.y = bubbleParams.y + dp(56);
        try {
            windowManager.updateViewLayout(panel, panelParams);
        } catch (Exception ignored) {
        }
        labelInput.requestFocus();
    }

    private void hidePanel() {
        pendingNodeId = 0;
        if (panel != null) {
            panel.setVisibility(View.GONE);
        }
    }

    private void removeView(View view) {
        if (windowManager != null && view != null) {
            try {
                windowManager.removeView(view);
            } catch (Exception ignored) {
            }
        }
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
