package com.shuran.app;

import android.content.Context;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

final class TimeLogClient {
    private TimeLogClient() {}

    static JSONObject punch(Context context, String label) throws Exception {
        JSONObject body = new JSONObject();
        if (label != null && !label.trim().isEmpty()) {
            body.put("label", label.trim());
        }
        return request(context, "POST", "/api/time-log/nodes", body);
    }

    static JSONObject updateLabel(Context context, int nodeId, String label) throws Exception {
        JSONObject body = new JSONObject();
        body.put("label", label == null ? "" : label.trim());
        return request(context, "POST", "/api/time-log/nodes/" + nodeId, body);
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
            conn.setRequestProperty("Content-Type", "application/json");
            conn.setConnectTimeout(8000);
            conn.setReadTimeout(8000);
            conn.setDoOutput(true);
            byte[] raw = body.toString().getBytes(StandardCharsets.UTF_8);
            conn.setFixedLengthStreamingMode(raw.length);
            OutputStream out = conn.getOutputStream();
            out.write(raw);
            out.close();
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
