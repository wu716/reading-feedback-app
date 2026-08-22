package com.shuran.app;

import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import android.util.Log;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.Toast;

import androidx.core.content.FileProvider;

import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * 同包名 + 更高 versionCode 即为覆盖更新，不必卸载。
 */
public class AppUpdater {
    static final int REQUEST_INSTALL_UNKNOWN = 1004;
    private static final String TAG = "ShuranUpdate";
    private static final String META_PATH = "/download/info";

    private final MainActivity activity;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private volatile boolean downloading;
    private volatile boolean cancelled;
    private File pendingApk;
    private AlertDialog progressDialog;
    private ProgressBar progressBar;

    AppUpdater(MainActivity activity) {
        this.activity = activity;
    }

    static int currentVersionCode(MainActivity activity) {
        try {
            PackageInfo info = activity.getPackageManager().getPackageInfo(activity.getPackageName(), 0);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                return (int) info.getLongVersionCode();
            }
            return info.versionCode;
        } catch (Exception e) {
            return 0;
        }
    }

    static String currentVersionName(MainActivity activity) {
        try {
            return activity.getPackageManager().getPackageInfo(activity.getPackageName(), 0).versionName;
        } catch (Exception e) {
            return "0";
        }
    }

    void check(boolean fromUser) {
        if (downloading) {
            if (fromUser) {
                Toast.makeText(activity, R.string.update_downloading, Toast.LENGTH_SHORT).show();
            }
            return;
        }
        executor.execute(() -> {
            try {
                JSONObject info = fetchInfo();
                activity.runOnUiThread(() -> handleInfo(info, fromUser));
            } catch (Exception e) {
                Log.e(TAG, "check failed", e);
                if (fromUser) {
                    activity.runOnUiThread(() -> Toast.makeText(
                            activity, R.string.update_check_failed, Toast.LENGTH_LONG).show());
                }
            }
        });
    }

    void onInstallPermissionResult() {
        if (pendingApk != null && pendingApk.isFile()) {
            installApk(pendingApk);
        }
    }

    private JSONObject fetchInfo() throws Exception {
        String base = activity.getString(R.string.app_url).replaceAll("/+$", "");
        HttpURLConnection conn = (HttpURLConnection) new URL(base + META_PATH).openConnection();
        conn.setConnectTimeout(12000);
        conn.setReadTimeout(12000);
        conn.setRequestProperty("Accept", "application/json");
        conn.setRequestProperty("Cache-Control", "no-cache");
        try {
            int code = conn.getResponseCode();
            if (code != 200) {
                throw new IllegalStateException("HTTP " + code);
            }
            InputStream in = conn.getInputStream();
            StringBuilder sb = new StringBuilder();
            byte[] buf = new byte[4096];
            int n;
            while ((n = in.read(buf)) > 0) {
                sb.append(new String(buf, 0, n, "UTF-8"));
            }
            return new JSONObject(sb.toString());
        } finally {
            conn.disconnect();
        }
    }

    private void handleInfo(JSONObject info, boolean fromUser) {
        if (activity.isFinishing()) {
            return;
        }
        boolean available = info.optBoolean("available", false);
        int latestCode = info.optInt("versionCode", 0);
        String latestName = info.optString("versionName", "");
        String notes = info.optString("notes", "");
        int currentCode = currentVersionCode(activity);
        String currentName = currentVersionName(activity);

        if (!available) {
            if (fromUser) {
                Toast.makeText(activity, R.string.update_not_uploaded, Toast.LENGTH_LONG).show();
            }
            return;
        }
        if (latestCode <= currentCode) {
            if (fromUser) {
                Toast.makeText(
                        activity,
                        activity.getString(R.string.update_already_latest, currentName),
                        Toast.LENGTH_LONG
                ).show();
            }
            return;
        }

        // Always download from the baked-in server URL, not a possibly-internal host.
        String downloadUrl = activity.getString(R.string.app_url).replaceAll("/+$", "") + "/download/apk";

        String message = activity.getString(
                R.string.update_message,
                currentName,
                latestName.isEmpty() ? String.valueOf(latestCode) : latestName
        );
        if (notes != null && !notes.trim().isEmpty()) {
            message = message + "\n\n" + notes.trim();
        }

        final String url = downloadUrl;
        new AlertDialog.Builder(activity)
                .setTitle(R.string.update_title)
                .setMessage(message)
                .setPositiveButton(R.string.update_now, (d, w) -> startDownload(url))
                .setNegativeButton(R.string.update_later, null)
                .show();
    }

    private void startDownload(String url) {
        if (downloading) {
            return;
        }
        downloading = true;
        cancelled = false;

        int pad = (int) (20 * activity.getResources().getDisplayMetrics().density);
        LinearLayout wrap = new LinearLayout(activity);
        wrap.setOrientation(LinearLayout.VERTICAL);
        wrap.setPadding(pad, pad / 2, pad, 0);
        progressBar = new ProgressBar(activity, null, android.R.attr.progressBarStyleHorizontal);
        progressBar.setMax(100);
        wrap.addView(progressBar);

        progressDialog = new AlertDialog.Builder(activity)
                .setTitle(R.string.update_downloading)
                .setMessage(R.string.update_download_hint)
                .setView(wrap)
                .setNegativeButton(R.string.update_cancel, (d, w) -> cancelled = true)
                .setCancelable(false)
                .show();

        executor.execute(() -> downloadAndInstall(url));
    }

    private void downloadAndInstall(String url) {
        File dir = new File(activity.getCacheDir(), "updates");
        if (!dir.exists() && !dir.mkdirs()) {
            failDownload(activity.getString(R.string.update_download_failed));
            return;
        }
        File apk = new File(dir, "shuran-update.apk");
        if (apk.exists() && !apk.delete()) {
            Log.w(TAG, "could not delete old apk");
        }

        HttpURLConnection conn = null;
        try {
            conn = (HttpURLConnection) new URL(url).openConnection();
            conn.setConnectTimeout(20000);
            conn.setReadTimeout(60000);
            conn.setInstanceFollowRedirects(true);
            conn.connect();
            int status = conn.getResponseCode();
            if (status != 200) {
                throw new IllegalStateException("HTTP " + status);
            }
            int total = conn.getContentLength();
            InputStream in = conn.getInputStream();
            FileOutputStream out = new FileOutputStream(apk);
            byte[] buf = new byte[16384];
            long read = 0;
            int n;
            int lastPct = -1;
            while ((n = in.read(buf)) > 0) {
                if (cancelled) {
                    out.close();
                    in.close();
                    apk.delete();
                    activity.runOnUiThread(() -> finishDownloadUi(true));
                    return;
                }
                out.write(buf, 0, n);
                read += n;
                if (total > 0) {
                    int pct = (int) (read * 100 / total);
                    if (pct != lastPct) {
                        lastPct = pct;
                        final int publish = pct;
                        activity.runOnUiThread(() -> {
                            if (progressBar != null) {
                                progressBar.setProgress(publish);
                            }
                        });
                    }
                }
            }
            out.flush();
            out.close();
            in.close();
            if (apk.length() < 1024) {
                throw new IllegalStateException("apk too small");
            }
            activity.runOnUiThread(() -> {
                finishDownloadUi(true);
                installApk(apk);
            });
        } catch (Exception e) {
            Log.e(TAG, "download failed", e);
            apk.delete();
            failDownload(activity.getString(R.string.update_download_failed));
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
            downloading = false;
        }
    }

    private void failDownload(String message) {
        activity.runOnUiThread(() -> {
            finishDownloadUi(true);
            Toast.makeText(activity, message, Toast.LENGTH_LONG).show();
        });
        downloading = false;
    }

    private void finishDownloadUi(boolean dismiss) {
        if (progressDialog != null) {
            if (dismiss) {
                try {
                    progressDialog.dismiss();
                } catch (Exception ignored) {
                }
            }
            progressDialog = null;
            progressBar = null;
        }
        if (cancelled) {
            downloading = false;
        }
    }

    private void installApk(File apk) {
        if (apk == null || !apk.isFile()) {
            Toast.makeText(activity, R.string.update_download_failed, Toast.LENGTH_LONG).show();
            return;
        }
        pendingApk = apk;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                && !activity.getPackageManager().canRequestPackageInstalls()) {
            Toast.makeText(activity, R.string.update_allow_install, Toast.LENGTH_LONG).show();
            Intent intent = new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES);
            intent.setData(Uri.parse("package:" + activity.getPackageName()));
            activity.startActivityForResult(intent, REQUEST_INSTALL_UNKNOWN);
            return;
        }
        launchInstaller(apk);
    }

    private void launchInstaller(File apk) {
        try {
            Uri uri = FileProvider.getUriForFile(
                    activity,
                    activity.getPackageName() + ".fileprovider",
                    apk
            );
            Intent intent = new Intent(Intent.ACTION_VIEW);
            intent.setDataAndType(uri, "application/vnd.android.package-archive");
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            PackageManager pm = activity.getPackageManager();
            List<ResolveInfo> resInfoList = pm.queryIntentActivities(intent, PackageManager.MATCH_DEFAULT_ONLY);
            for (ResolveInfo resolveInfo : resInfoList) {
                activity.grantUriPermission(
                        resolveInfo.activityInfo.packageName,
                        uri,
                        Intent.FLAG_GRANT_READ_URI_PERMISSION
                );
            }
            activity.startActivity(intent);
        } catch (Exception e) {
            Log.e(TAG, "install launch failed", e);
            Toast.makeText(activity, R.string.update_install_failed, Toast.LENGTH_LONG).show();
        }
    }
}
