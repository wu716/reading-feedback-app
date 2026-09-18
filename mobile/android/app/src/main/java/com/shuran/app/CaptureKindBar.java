package com.shuran.app;

import android.content.Context;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.util.AttributeSet;
import android.util.TypedValue;
import android.view.Gravity;
import android.widget.Button;
import android.widget.LinearLayout;

/**
 * 快捷记下的去处：moment / idea / todo；todo 再选 today 或 later。
 */
public class CaptureKindBar extends LinearLayout {
    public interface Listener {
        void onChanged(String kind, String todoWhen);
    }

    private static final int ON_BG = 0xFF1C1B19;
    private static final int ON_FG = 0xFFF3EFE6;
    private static final int OFF_BG = 0x00000000;
    private static final int OFF_FG = 0xFF1C1B19;

    private final Button moment;
    private final Button idea;
    private final Button todo;
    private final LinearLayout whenRow;
    private final Button today;
    private final Button later;
    private String kind = CaptureKinds.MOMENT;
    private String todoWhen = CaptureKinds.TODAY;
    private Listener listener;

    public CaptureKindBar(Context context) {
        this(context, null);
    }

    public CaptureKindBar(Context context, AttributeSet attrs) {
        super(context, attrs);
        setOrientation(VERTICAL);
        LinearLayout kindRow = new LinearLayout(context);
        kindRow.setOrientation(HORIZONTAL);
        kindRow.setGravity(Gravity.CENTER);
        moment = chip(context, context.getString(R.string.capture_kind_moment));
        idea = chip(context, context.getString(R.string.capture_kind_idea));
        todo = chip(context, context.getString(R.string.capture_kind_todo));
        kindRow.addView(moment, chipParams());
        kindRow.addView(idea, chipParams());
        kindRow.addView(todo, chipParams());
        addView(kindRow, new LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT));

        whenRow = new LinearLayout(context);
        whenRow.setOrientation(HORIZONTAL);
        whenRow.setGravity(Gravity.CENTER);
        LayoutParams whenParams = new LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT);
        whenParams.topMargin = dp(6);
        today = chip(context, context.getString(R.string.capture_when_today));
        later = chip(context, context.getString(R.string.capture_when_later));
        whenRow.addView(today, chipParams());
        whenRow.addView(later, chipParams());
        addView(whenRow, whenParams);

        moment.setOnClickListener(v -> setKind(CaptureKinds.MOMENT, true));
        idea.setOnClickListener(v -> setKind(CaptureKinds.IDEA, true));
        todo.setOnClickListener(v -> setKind(CaptureKinds.TODO, true));
        today.setOnClickListener(v -> setTodoWhen(CaptureKinds.TODAY, true));
        later.setOnClickListener(v -> setTodoWhen(CaptureKinds.LATER, true));
        paint();
    }

    public void setListener(Listener listener) {
        this.listener = listener;
    }

    public String kind() {
        return kind;
    }

    public String todoWhen() {
        return todoWhen;
    }

    public void setKind(String next) {
        setKind(next, false);
    }

    private void setKind(String next, boolean notify) {
        kind = CaptureKinds.normalizeKind(next);
        paint();
        if (notify && listener != null) {
            listener.onChanged(kind, todoWhen);
        }
    }

    private void setTodoWhen(String next, boolean notify) {
        todoWhen = CaptureKinds.normalizeWhen(next);
        paint();
        if (notify && listener != null) {
            listener.onChanged(kind, todoWhen);
        }
    }

    private void paint() {
        paintChip(moment, CaptureKinds.MOMENT.equals(kind));
        paintChip(idea, CaptureKinds.IDEA.equals(kind));
        paintChip(todo, CaptureKinds.TODO.equals(kind));
        paintChip(today, CaptureKinds.TODAY.equals(todoWhen));
        paintChip(later, CaptureKinds.LATER.equals(todoWhen));
        whenRow.setVisibility(CaptureKinds.TODO.equals(kind) ? VISIBLE : GONE);
    }

    private Button chip(Context context, String label) {
        Button button = new Button(context, null, android.R.attr.borderlessButtonStyle);
        button.setText(label);
        button.setAllCaps(false);
        button.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
        button.setMinHeight(dp(34));
        button.setPadding(dp(4), dp(4), dp(4), dp(4));
        return button;
    }

    private LayoutParams chipParams() {
        LayoutParams params = new LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f);
        params.setMarginStart(dp(3));
        params.setMarginEnd(dp(3));
        return params;
    }

    private void paintChip(Button button, boolean on) {
        GradientDrawable bg = new GradientDrawable();
        bg.setCornerRadius(dp(8));
        if (on) {
            bg.setColor(ON_BG);
            button.setTextColor(ON_FG);
        } else {
            bg.setColor(Color.TRANSPARENT);
            bg.setStroke(Math.max(1, dp(1)), OFF_FG);
            button.setTextColor(OFF_FG);
        }
        button.setBackground(bg);
    }

    private int dp(int value) {
        return Math.round(TypedValue.applyDimension(
                TypedValue.COMPLEX_UNIT_DIP, value, getResources().getDisplayMetrics()));
    }
}
