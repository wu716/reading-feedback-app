package com.shuran.app;

import android.content.Context;
import android.os.Build;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

final class TimeLogClient {
    private TimeLogClient() {}

    static String nowIso() {
        SimpleDateFormat fmt = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US);
        fmt.setTimeZone(TimeZone.getTimeZone("Asia/Shanghai"));
        return fmt.format(new Date());
    }

    static JSONObject dayLog(Context context) throws Exception {
        return request(context, "GET", "/api/time-log", null);
    }

    static JSONObject punch(Context context, String label) throws Exception {
        return punch(context, label, nowIso());
    }

    static JSONObject punch(Context context, String label, String loggedAtIso) throws Exception {
        return capture(context, CaptureKinds.MOMENT, label, null, loggedAtIso);
    }

    static JSONObject capture(
            Context context,
            String kind,
            String label,
            String todoWhen,
            String loggedAtIso
    ) throws Exception {
        JSONObject body = new JSONObject();
        body.put("kind", CaptureKinds.normalizeKind(kind));
        if (label != null && !label.trim().isEmpty()) {
            body.put("text", label.trim());
        }
        if (CaptureKinds.TODO.equals(CaptureKinds.normalizeKind(kind))) {
            body.put("todo_when", CaptureKinds.normalizeWhen(todoWhen));
        }
        if (CaptureKinds.MOMENT.equals(CaptureKinds.normalizeKind(kind))
                && loggedAtIso != null
                && !loggedAtIso.isEmpty()) {
            body.put("logged_at", loggedAtIso);
        }
        return request(context, "POST", "/api/capture/save", body);
    }

    static String preferenceKind(Context context) {
        return CaptureKinds.normalizeKind(
                ReminderScheduler.prefs(context).getString(CaptureKinds.PREF_KIND, CaptureKinds.MOMENT)
        );
    }

    static void cachePreferenceKind(Context context, String kind) {
        ReminderScheduler.prefs(context)
                .edit()
                .putString(CaptureKinds.PREF_KIND, CaptureKinds.normalizeKind(kind))
                .apply();
    }

    static String fetchPreferenceKind(Context context) throws Exception {
        JSONObject data = request(context, "GET", "/api/capture/preference", null);
        String kind = CaptureKinds.normalizeKind(data.optString("kind", CaptureKinds.MOMENT));
        cachePreferenceKind(context, kind);
        return kind;
    }

    static JSONObject updateLabel(Context context, int nodeId, String label) throws Exception {
        JSONObject body = new JSONObject();
        body.put("label", label == null ? "" : label.trim());
        return request(context, "POST", "/api/time-log/nodes/" + nodeId, body);
    }

    static JSONObject deleteNode(Context context, int nodeId) throws Exception {
        return request(context, "DELETE", "/api/time-log/nodes/" + nodeId, null);
    }

    static int durationSinceLast(JSONObject day, long clickedAtMs) {
        if (day == null) {
            return 0;
        }
        JSONArray nodes = day.optJSONArray("nodes");
        if (nodes == null || nodes.length() == 0) {
            return 0;
        }
        try {
            String logged = nodes.getJSONObject(nodes.length() - 1).optString("logged_at", "");
            long prev = parseIsoMillis(logged);
            if (prev <= 0) {
                return 0;
            }
            return (int) Math.max(0, (clickedAtMs - prev) / 1000L);
        } catch (Exception e) {
            return 0;
        }
    }

    static long parseIsoMillis(String iso) {
        if (iso == null || iso.isEmpty()) {
            return 0;
        }
        try {
            if (Build.VERSION.SDK_INT >= 26) {
                return java.time.OffsetDateTime.parse(iso).toInstant().toEpochMilli();
            }
        } catch (Exception ignored) {
        }
        try {
            String stripped = iso.replaceAll("\\.\\d+", "");
            SimpleDateFormat fmt = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US);
            Date parsed = fmt.parse(stripped);
            return parsed == null ? 0 : parsed.getTime();
        } catch (Exception e) {
            return 0;
        }
    }

    private static JSONObject request(Context context, String method, String path, JSONObject body) throws Exception {
        String token = ReminderScheduler.sessionToken(context);
        if (token.isEmpty()) {
            throw new IllegalStateException("请先登录");
        }
        URL url = new URL(ReminderScheduler.apiOrigin(context) + path);
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        try {
            conn.setRequestMethod(method);
            conn.setRequestProperty("Authorization", "Bearer " + token);
            conn.setRequestProperty("Accept", "application/json");
            conn.setConnectTimeout(8000);
            conn.setReadTimeout(8000);
            if (body != null) {
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setDoOutput(true);
                byte[] raw = body.toString().getBytes(StandardCharsets.UTF_8);
                conn.setFixedLengthStreamingMode(raw.length);
                OutputStream out = conn.getOutputStream();
                out.write(raw);
                out.close();
            }
            int code = conn.getResponseCode();
            InputStream stream = code >= 400 ? conn.getErrorStream() : conn.getInputStream();
            String text = readAll(stream);
            if (code >= 400) {
                String detail = text;
                try {
                    detail = new JSONObject(text).optString("detail", text);
                } catch (Exception ignored) {
                }
                throw new IllegalStateException(detail == null || detail.isEmpty() ? ("请求失败 " + code) : detail);
            }
            if (text == null || text.isEmpty()) {
                return new JSONObject();
            }
            return new JSONObject(text);
        } finally {
            conn.disconnect();
        }
    }

    private static String readAll(InputStream stream) throws Exception {
        if (stream == null) {
            return "";
        }
        BufferedReader reader = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8));
        StringBuilder sb = new StringBuilder();
        String line;
        while ((line = reader.readLine()) != null) {
            sb.append(line);
        }
        reader.close();
        return sb.toString();
    }
}
