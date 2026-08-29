package com.shuran.app;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.KeyEvent;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.PermissionRequest;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

import androidx.core.content.ContextCompat;

public class MainActivity extends Activity {
    private static final int FILE_CHOOSER_REQUEST = 1001;
    private static final int AUDIO_PERMISSION_REQUEST = 1002;
    private static final int NOTIFICATION_PERMISSION_REQUEST = 1003;

    private WebView webView;
    private ProgressBar progressBar;
    private LinearLayout errorView;
    private ValueCallback<Uri[]> filePathCallback;
    private PermissionRequest pendingPermissionRequest;
    private long lastBackHandledAt;
    private boolean notificationPermissionRequested;
    private boolean updateChecked;
    private AppUpdater appUpdater;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        webView = findViewById(R.id.webview);
        progressBar = findViewById(R.id.progress);
        errorView = findViewById(R.id.error_view);
        Button retryButton = findViewById(R.id.retry_button);
        TextView errorText = findViewById(R.id.error_text);
        errorText.setText(R.string.network_error);
        retryButton.setOnClickListener(v -> loadApp());

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setSupportZoom(false);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        settings.setCacheMode(WebSettings.LOAD_NO_CACHE);
        webView.clearCache(true);
        settings.setUserAgentString(
                settings.getUserAgentString() + " ShuranApp/" + AppUpdater.currentVersionName(this)
        );

        appUpdater = new AppUpdater(this);
        ReminderNotifications.ensureChannel(this);
        webView.addJavascriptInterface(new ReminderJsBridge(this), "ShuranNative");
        webView.setDownloadListener((url, userAgent, contentDisposition, mimeType, contentLength) -> {
            if (url != null && (url.contains("/download/apk")
                    || "application/vnd.android.package-archive".equals(mimeType))) {
                checkAppUpdateFromUser();
                return;
            }
            try {
                startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
            } catch (Exception ignored) {
            }
        });

        webView.setOnKeyListener((v, keyCode, event) -> {
            if (keyCode != KeyEvent.KEYCODE_BACK) {
                return false;
            }
            if (event.getAction() != KeyEvent.ACTION_UP) {
                return true;
            }
            handleBackNavigation();
            return true;
        });

        CookieManager cookieManager = CookieManager.getInstance();
        cookieManager.setAcceptCookie(true);
        cookieManager.setAcceptThirdPartyCookies(webView, true);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                String path = uri.getPath();
                if (path != null && path.endsWith("/download/apk")) {
                    checkAppUpdateFromUser();
                    return true;
                }
                String scheme = uri.getScheme();
                if ("http".equalsIgnoreCase(scheme) || "https".equalsIgnoreCase(scheme)) {
                    return false;
                }
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, uri));
                } catch (Exception ignored) {
                }
                return true;
            }

            @Override
            public void onPageStarted(WebView view, String url, Bitmap favicon) {
                errorView.setVisibility(View.GONE);
                webView.setVisibility(View.VISIBLE);
                progressBar.setVisibility(View.VISIBLE);
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                progressBar.setVisibility(View.GONE);
                CookieManager.getInstance().flush();
                maybeCheckAppUpdate();
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    webView.setVisibility(View.GONE);
                    errorView.setVisibility(View.VISIBLE);
                    progressBar.setVisibility(View.GONE);
                }
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                progressBar.setProgress(newProgress);
                progressBar.setVisibility(newProgress >= 100 ? View.GONE : View.VISIBLE);
            }

            @Override
            public void onPermissionRequest(PermissionRequest request) {
                runOnUiThread(() -> handlePermissionRequest(request));
            }

            @Override
            public boolean onShowFileChooser(
                    WebView webView,
                    ValueCallback<Uri[]> filePathCallback,
                    FileChooserParams fileChooserParams) {
                if (MainActivity.this.filePathCallback != null) {
                    MainActivity.this.filePathCallback.onReceiveValue(null);
                }
                MainActivity.this.filePathCallback = filePathCallback;
                Intent intent = fileChooserParams.createIntent();
                try {
                    startActivityForResult(intent, FILE_CHOOSER_REQUEST);
                } catch (Exception e) {
                    MainActivity.this.filePathCallback = null;
                    return false;
                }
                return true;
            }
        });

        if (savedInstanceState != null) {
            webView.restoreState(savedInstanceState);
            applyOpenPath(getIntent());
        } else {
            loadApp(getIntent());
        }
    }

    void checkAppUpdateFromUser() {
        if (appUpdater != null) {
            appUpdater.check(true);
        }
    }

    private void maybeCheckAppUpdate() {
        if (updateChecked || appUpdater == null || errorView.getVisibility() == View.VISIBLE) {
            return;
        }
        updateChecked = true;
        webView.postDelayed(() -> {
            if (!isFinishing() && appUpdater != null) {
                appUpdater.check(false);
            }
        }, 1800);
    }

    void requestNotificationPermission() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
            return;
        }
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                == PackageManager.PERMISSION_GRANTED) {
            return;
        }
        if (notificationPermissionRequested) {
            return;
        }
        notificationPermissionRequested = true;
        requestPermissions(
                new String[]{Manifest.permission.POST_NOTIFICATIONS},
                NOTIFICATION_PERMISSION_REQUEST
        );
    }

    void openExactAlarmSettings() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) {
            return;
        }
        try {
            Intent intent = new Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM);
            intent.setData(Uri.parse("package:" + getPackageName()));
            startActivity(intent);
        } catch (Exception e) {
            try {
                startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                        .setData(Uri.parse("package:" + getPackageName())));
            } catch (Exception ignored) {
            }
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        applyOpenPath(intent);
    }

    private void handlePermissionRequest(PermissionRequest request) {
        boolean wantsAudio = false;
        for (String resource : request.getResources()) {
            if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(resource)) {
                wantsAudio = true;
                break;
            }
        }
        if (!wantsAudio) {
            request.grant(request.getResources());
            return;
        }
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            request.grant(request.getResources());
        } else {
            pendingPermissionRequest = request;
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, AUDIO_PERMISSION_REQUEST);
        }
    }

    private void loadApp() {
        loadApp(getIntent());
    }

    private void loadApp(Intent intent) {
        errorView.setVisibility(View.GONE);
        webView.setVisibility(View.VISIBLE);
        String path = intent != null ? intent.getStringExtra(ReminderNotifications.EXTRA_OPEN_PATH) : null;
        if (path != null && !path.isEmpty()) {
            intent.removeExtra(ReminderNotifications.EXTRA_OPEN_PATH);
            webView.loadUrl(withCacheBust(ReminderNotifications.resolveUrl(this, path)));
        } else {
            webView.loadUrl(appPageUrl());
        }
    }

    private String appPageUrl() {
        return withCacheBust(getString(R.string.app_url));
    }

    private String withCacheBust(String url) {
        if (url == null || url.isEmpty()) {
            return url;
        }
        String stamp = "ui=" + AppUpdater.currentVersionCode(this);
        return url.contains("?") ? url + "&" + stamp : url + "?" + stamp;
    }

    private void applyOpenPath(Intent intent) {
        if (intent == null || webView == null) {
            return;
        }
        String path = intent.getStringExtra(ReminderNotifications.EXTRA_OPEN_PATH);
        if (path == null || path.isEmpty()) {
            return;
        }
        intent.removeExtra(ReminderNotifications.EXTRA_OPEN_PATH);
        errorView.setVisibility(View.GONE);
        webView.setVisibility(View.VISIBLE);
        webView.loadUrl(withCacheBust(ReminderNotifications.resolveUrl(this, path)));
    }

    private void handleBackNavigation() {
        long now = System.currentTimeMillis();
        if (now - lastBackHandledAt < 400) {
            return;
        }
        lastBackHandledAt = now;

        if (errorView.getVisibility() == View.VISIBLE) {
            finish();
            return;
        }

        webView.evaluateJavascript(
                "(function(){try{if(typeof handleAppBack==='function')return handleAppBack();}catch(e){}return 'nav';})()",
                value -> {
                    String result = value == null ? "" : value.replace("\"", "");
                    if ("consumed".equals(result)) {
                        return;
                    }
                    if ("exit".equals(result)) {
                        finish();
                        return;
                    }
                    if (webView.canGoBack()) {
                        webView.goBack();
                    } else {
                        finish();
                    }
                });
    }

    @Override
    public void onBackPressed() {
        handleBackNavigation();
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == AppUpdater.REQUEST_INSTALL_UNKNOWN) {
            if (appUpdater != null) {
                appUpdater.onInstallPermissionResult();
            }
            return;
        }
        if (requestCode != FILE_CHOOSER_REQUEST || filePathCallback == null) {
            return;
        }
        Uri[] uris = WebChromeClient.FileChooserParams.parseResult(resultCode, data);
        filePathCallback.onReceiveValue(uris);
        filePathCallback = null;
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == NOTIFICATION_PERMISSION_REQUEST) {
            if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                ReminderScheduler.restore(getApplicationContext());
                ReminderScheduler.pollNow(getApplicationContext());
            }
            return;
        }
        if (requestCode != AUDIO_PERMISSION_REQUEST || pendingPermissionRequest == null) {
            return;
        }
        if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            pendingPermissionRequest.grant(pendingPermissionRequest.getResources());
        } else {
            pendingPermissionRequest.deny();
        }
        pendingPermissionRequest = null;
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        webView.saveState(outState);
    }

    @Override
    protected void onPause() {
        super.onPause();
        webView.onPause();
        CookieManager.getInstance().flush();
    }

    @Override
    protected void onResume() {
        super.onResume();
        webView.onResume();
        ReminderScheduler.restore(this);
        webView.evaluateJavascript(
                "(function(){try{if(window.reminderNotificationService&&window.reminderNotificationService.refreshReliabilityHints){window.reminderNotificationService.refreshReliabilityHints();}}catch(e){}})()",
                null
        );
    }

    @Override
    protected void onDestroy() {
        webView.loadUrl("about:blank");
        webView.stopLoading();
        webView.destroy();
        super.onDestroy();
    }
}
