package com.shuran.app;

import android.Manifest;
import android.content.pm.PackageManager;
import android.media.MediaRecorder;
import android.os.Build;
import android.util.Log;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;

import org.json.JSONObject;

import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.util.Collections;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

/**
 * App 内 Self-talk 原生录音。产出 AAC/m4a，由网页再走 POST /api/self_talks/。
 */
public class NativeRecorder {
    private static final String TAG = "ShuranRecorder";
    static final String INTERCEPT_PATH = "/__shuran_native_recording";
    private static final String MIME = "audio/mp4";
    private static final String FILENAME = "recording.m4a";
    private static final long MAX_BYTES = 50L * 1024 * 1024;
    private static final int MAX_DURATION_MS = 30 * 60 * 1000;

    private final MainActivity activity;
    private MediaRecorder recorder;
    private File outputFile;
    private File readyFile;
    private boolean recording;

    NativeRecorder(MainActivity activity) {
        this.activity = activity;
    }

    boolean hasPermission() {
        return activity.checkSelfPermission(Manifest.permission.RECORD_AUDIO)
                == PackageManager.PERMISSION_GRANTED;
    }

    synchronized boolean isRecording() {
        return recording;
    }

    synchronized String start() {
        JSONObject json = new JSONObject();
        try {
            if (recording) {
                json.put("ok", false);
                json.put("code", "busy");
                json.put("message", "正在录音");
                return json.toString();
            }
            if (!hasPermission()) {
                json.put("ok", false);
                json.put("code", "need_permission");
                json.put("message", "需要麦克风权限");
                return json.toString();
            }

            File dir = new File(activity.getCacheDir(), "recordings");
            if (!dir.exists() && !dir.mkdirs()) {
                json.put("ok", false);
                json.put("code", "error");
                json.put("message", "现在没法录音，请再试一次");
                return json.toString();
            }

            deleteQuiet(outputFile);
            deleteQuiet(readyFile);
            readyFile = null;
            outputFile = new File(dir, FILENAME);
            if (outputFile.exists() && !outputFile.delete()) {
                Log.w(TAG, "could not delete old recording");
            }

            MediaRecorder next = createRecorder();
            next.setAudioSource(MediaRecorder.AudioSource.MIC);
            next.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4);
            next.setAudioEncoder(MediaRecorder.AudioEncoder.AAC);
            next.setAudioEncodingBitRate(128000);
            next.setAudioSamplingRate(44100);
            next.setAudioChannels(1);
            try {
                next.setMaxFileSize(MAX_BYTES);
            } catch (Exception ignored) {
            }
            try {
                next.setMaxDuration(MAX_DURATION_MS);
            } catch (Exception ignored) {
            }
            next.setOutputFile(outputFile.getAbsolutePath());
            next.setOnInfoListener((mr, what, extra) -> {
                if (what == MediaRecorder.MEDIA_RECORDER_INFO_MAX_FILESIZE_REACHED
                        || what == MediaRecorder.MEDIA_RECORDER_INFO_MAX_DURATION_REACHED) {
                    activity.runOnUiThread(() ->
                            activity.notifyNativeRecordingStopped(stop()));
                }
            });
            next.setOnErrorListener((mr, what, extra) -> {
                Log.e(TAG, "MediaRecorder error what=" + what + " extra=" + extra);
                activity.runOnUiThread(() -> {
                    cancel();
                    activity.notifyNativeRecordingStopped(
                            errorJson("recorder_error", "录音中断了，请再试一次"));
                });
            });
            next.prepare();
            next.start();
            recorder = next;
            recording = true;
            json.put("ok", true);
            json.put("code", "ok");
            return json.toString();
        } catch (Exception e) {
            Log.e(TAG, "start failed", e);
            releaseRecorder();
            recording = false;
            deleteQuiet(outputFile);
            String[] classified = classifyStartError(e);
            try {
                json.put("ok", false);
                json.put("code", classified[0]);
                json.put("message", classified[1]);
            } catch (Exception ignored) {
            }
            return json.toString();
        }
    }

    synchronized String stop() {
        if (!recording && readyFile == null) {
            return errorJson("idle", "当前没有录音");
        }
        if (!recording && readyFile != null) {
            return successJson(readyFile);
        }
        releaseRecorder();
        recording = false;
        if (outputFile == null || !outputFile.exists() || outputFile.length() <= 0) {
            deleteQuiet(outputFile);
            outputFile = null;
            readyFile = null;
            return errorJson("empty", "没有录到声音，请靠近麦克风再试");
        }
        if (outputFile.length() > MAX_BYTES) {
            deleteQuiet(outputFile);
            outputFile = null;
            readyFile = null;
            return errorJson("too_large", "录音太长了，请录短一点再试");
        }
        readyFile = outputFile;
        return successJson(readyFile);
    }

    synchronized String readBase64() {
        if (readyFile == null || !readyFile.exists() || readyFile.length() <= 0) {
            return "";
        }
        if (readyFile.length() > 5L * 1024 * 1024) {
            return "";
        }
        FileInputStream in = null;
        try {
            byte[] data = new byte[(int) readyFile.length()];
            in = new FileInputStream(readyFile);
            int offset = 0;
            while (offset < data.length) {
                int n = in.read(data, offset, data.length - offset);
                if (n < 0) {
                    break;
                }
                offset += n;
            }
            return android.util.Base64.encodeToString(data, android.util.Base64.NO_WRAP);
        } catch (Exception e) {
            Log.e(TAG, "readBase64 failed", e);
            return "";
        } finally {
            if (in != null) {
                try {
                    in.close();
                } catch (Exception ignored) {
                }
            }
        }
    }

    synchronized String cancel() {
        releaseRecorder();
        recording = false;
        deleteQuiet(outputFile);
        deleteQuiet(readyFile);
        outputFile = null;
        readyFile = null;
        JSONObject json = new JSONObject();
        try {
            json.put("ok", true);
            json.put("code", "cancelled");
        } catch (Exception ignored) {
        }
        return json.toString();
    }

    synchronized void release() {
        cancel();
    }

    synchronized WebResourceResponse intercept(WebResourceRequest request) {
        if (request == null || request.getUrl() == null) {
            return null;
        }
        if (!INTERCEPT_PATH.equals(request.getUrl().getPath())) {
            return null;
        }
        File file = readyFile;
        if (file == null || !file.exists()) {
            return new WebResourceResponse(
                    "text/plain",
                    "utf-8",
                    404,
                    "Not Found",
                    Collections.emptyMap(),
                    new ByteArrayInputStream(new byte[0])
            );
        }
        try {
            Map<String, String> headers = new HashMap<>();
            headers.put("Content-Type", MIME);
            headers.put("Content-Length", String.valueOf(file.length()));
            headers.put("Cache-Control", "no-store");
            return new WebResourceResponse(
                    MIME,
                    null,
                    200,
                    "OK",
                    headers,
                    new FileInputStream(file)
            );
        } catch (Exception e) {
            Log.e(TAG, "intercept failed", e);
            return new WebResourceResponse(
                    "text/plain",
                    "utf-8",
                    500,
                    "Error",
                    Collections.emptyMap(),
                    new ByteArrayInputStream(new byte[0])
            );
        }
    }

    @SuppressWarnings("deprecation")
    private MediaRecorder createRecorder() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            return new MediaRecorder(activity);
        }
        return new MediaRecorder();
    }

    private void releaseRecorder() {
        MediaRecorder current = recorder;
        recorder = null;
        if (current == null) {
            return;
        }
        try {
            current.stop();
        } catch (Exception ignored) {
        }
        try {
            current.reset();
        } catch (Exception ignored) {
        }
        try {
            current.release();
        } catch (Exception ignored) {
        }
    }

    private static void deleteQuiet(File file) {
        if (file != null && file.exists()) {
            //noinspection ResultOfMethodCallIgnored
            file.delete();
        }
    }

    private static String successJson(File file) {
        JSONObject json = new JSONObject();
        try {
            json.put("ok", true);
            json.put("code", "ok");
            json.put("url", INTERCEPT_PATH);
            json.put("filename", FILENAME);
            json.put("mimeType", MIME);
            json.put("size", file.length());
        } catch (Exception ignored) {
        }
        return json.toString();
    }

    private String[] classifyStartError(Exception e) {
        String detail = e.getMessage() == null ? "" : e.getMessage();
        String lower = detail.toLowerCase(Locale.US);
        boolean permissionLike = e instanceof SecurityException
                || lower.contains("permission")
                || lower.contains("denied");
        if (permissionLike) {
            if (hasPermission()) {
                return new String[]{"blocked", "系统拦截了录音，请到设置里打开麦克风"};
            }
            return new String[]{"need_permission", "需要麦克风才能录音"};
        }
        if (e instanceof RuntimeException) {
            return new String[]{"mic_busy", "麦克风正被占用，请关掉其他正在录音的应用后再试"};
        }
        return new String[]{"recorder_error", "现在没法录音，请再试一次"};
    }

    private static String errorJson(String code, String message) {
        JSONObject json = new JSONObject();
        try {
            json.put("ok", false);
            json.put("code", code == null ? "error" : code);
            json.put("message", message);
        } catch (Exception ignored) {
        }
        return json.toString();
    }
}
