using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace Shuran.Desktop;

sealed class MainForm : Form
{
    const string WebView2RuntimeUrl = "https://go.microsoft.com/fwlink/p/?LinkId=2124703";
    const int HotkeyIdCapture = 1;
    readonly string _startUrl;
    readonly string? _userDataFolder;
    readonly ConnectionRecoveryView _connectionView = new() { Visible = false };
    readonly NavigationRecovery _recovery = new();
    CancellationTokenSource? _retryCancellation;
    CancellationTokenSource? _navigationCancellation;
    ulong? _navigationId;
    string _lastDiagnostic = "";
    readonly WebView2 _webView = new()
    {
        Dock = DockStyle.Fill,
        DefaultBackgroundColor = Color.White
    };
    bool _hotkeyRegistered;
    bool _webReady;
    FocusReminders? _focusReminders;

    public MainForm(string startUrl, string? userDataFolder = null)
    {
        _startUrl = startUrl;
        _userDataFolder = userDataFolder;
        Text = "书然";
        try
        {
            Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        }
        catch
        {
            /* ApplicationIcon on the exe is enough for the desktop shortcut */
        }
        Width = 1180;
        Height = 800;
        MinimumSize = new Size(420, 560);
        StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.Sizable;
        AutoScaleMode = AutoScaleMode.Dpi;
        KeyPreview = true;
        Controls.Add(_webView);
        Controls.Add(_connectionView);
        _connectionView.RetryRequested += () => Connect(reset: true);
        _connectionView.StopRequested += StopRecovery;
        Load += async (_, _) => await StartBrowserAsync();
        FormClosed += (_, _) =>
        {
            CancelRetry();
            CancelNavigation();
            UnregisterCaptureHotkey();
            _focusReminders?.Dispose();
        };
    }

    protected override void WndProc(ref Message m)
    {
        if (m.Msg == NativeMethods.WmActivateShuran)
        {
            BringToFrontSafe();
            if (m.WParam != IntPtr.Zero)
            {
                _ = OpenCaptureAsync();
            }
            return;
        }

        if (m.Msg == NativeMethods.WmHotkey && m.WParam.ToInt32() == HotkeyIdCapture)
        {
            BringToFrontSafe();
            _ = OpenCaptureAsync();
            return;
        }

        base.WndProc(ref m);
    }

    async Task StartBrowserAsync()
    {
        try
        {
            var userData = _userDataFolder ?? Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Shuran",
                "WebView2");
            Directory.CreateDirectory(userData);
            var env = await CoreWebView2Environment.CreateAsync(null, userData);
            await _webView.EnsureCoreWebView2Async(env);
        }
        catch (WebView2RuntimeNotFoundException)
        {
            ShowRuntimeMissing();
            Close();
            return;
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                "无法启动内置网页引擎。\n请安装 Microsoft Edge WebView2 Runtime 后重试。\n\n" + WebView2RuntimeUrl + "\n\n" + ex.Message,
                "书然",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            Close();
            return;
        }

        _webView.ZoomFactor = 1;
        var settings = _webView.CoreWebView2.Settings;
        settings.AreDefaultContextMenusEnabled = true;
        settings.AreBrowserAcceleratorKeysEnabled = true;
        settings.IsZoomControlEnabled = true;
        settings.IsPinchZoomEnabled = false;
        settings.IsStatusBarEnabled = false;
        var appVersion = Application.ProductVersion.Split('+')[0];
        _webView.CoreWebView2.Settings.UserAgent += $" ShuranDesktop/{appVersion}";
        _focusReminders = new FocusReminders(() => BeginInvoke((Action)(() =>
        {
            BringToFrontSafe();
            _webView.CoreWebView2.Navigate(new Uri(new Uri(_startUrl), "/static/projects.html#execution").AbsoluteUri);
        })));
        _webView.CoreWebView2.WebMessageReceived += (_, e) =>
        {
            // Only the configured app origin may schedule local notifications.
            if (!Uri.TryCreate(e.Source, UriKind.Absolute, out var source)
                || source.GetLeftPart(UriPartial.Authority) != new Uri(_startUrl).GetLeftPart(UriPartial.Authority)) return;
            try
            {
                using var message = System.Text.Json.JsonDocument.Parse(e.WebMessageAsJson);
                if (message.RootElement.GetProperty("type").GetString() == "focusTimer")
                    _focusReminders.Sync(message.RootElement.GetProperty("data"));
            }
            catch (Exception ex) { System.Diagnostics.Trace.WriteLine("Focus bridge: " + ex.Message); }
        };
        _webView.CoreWebView2.NewWindowRequested += (_, e) =>
        {
            e.Handled = true;
            _webView.CoreWebView2.Navigate(e.Uri);
        };
        _webView.CoreWebView2.NavigationStarting += OnNavigationStarting;
        _webView.CoreWebView2.NavigationCompleted += OnNavigationCompleted;
        try
        {
            await _webView.CoreWebView2.Profile.ClearBrowsingDataAsync(
                CoreWebView2BrowsingDataKinds.DiskCache);
        }
        catch
        {
            /* older runtimes may not expose disk-cache-only clearing */
        }
        RegisterCaptureHotkey();
        Connect(reset: true);
        _ = CheckDesktopUpdateAsync();
    }

    void CancelRetry()
    {
        _retryCancellation?.Cancel();
        _retryCancellation?.Dispose();
        _retryCancellation = null;
    }

    void CancelNavigation()
    {
        _navigationCancellation?.Cancel();
        _navigationCancellation?.Dispose();
        _navigationCancellation = null;
    }

    void Connect(bool reset)
    {
        if (IsDisposed || _webView.CoreWebView2 is null) return;
        CancelRetry();
        CancelNavigation();
        _navigationId = null;
        if (reset) _recovery.Reset();
        else _recovery.BeginConnection();
        _webReady = false;
        _webView.Visible = false;
        _connectionView.ShowState("正在连接书然", "正在打开页面，请稍候。",
            _recovery.RetryCount == 0 ? "首次连接" : $"正在重试 {_recovery.RetryCount}/{NavigationRecovery.MaximumRetries}",
            _lastDiagnostic, true);
        // Navigate issues a new GET to the configured homepage, never a POST replay.
        _webView.CoreWebView2.Navigate(_startUrl);
    }

    void OnNavigationStarting(object? sender, CoreWebView2NavigationStartingEventArgs e)
    {
        CancelRetry();
        _webReady = false;
        _recovery.ObserveNavigation(e.NavigationId);
        if (_navigationId == e.NavigationId) return;
        CancelNavigation();
        _navigationId = e.NavigationId;
        if (!_recovery.CanRetryNavigation) return;
        _navigationCancellation = new CancellationTokenSource();
        _ = WatchNavigationAsync(e.NavigationId, _navigationCancellation.Token);
    }

    async Task WatchNavigationAsync(ulong navigationId, CancellationToken token)
    {
        try
        {
            await Task.Delay(TimeSpan.FromSeconds(15), token);
            if (token.IsCancellationRequested || IsDisposed || _navigationId != navigationId) return;
            _navigationId = null;
            _webView.CoreWebView2.Stop();
            HandleFailure(0, CoreWebView2WebErrorStatus.Timeout);
        }
        catch (OperationCanceledException) { }
    }

    void OnNavigationCompleted(object? sender, CoreWebView2NavigationCompletedEventArgs e)
    {
        if (_navigationId != e.NavigationId || IsDisposed) return;
        CancelNavigation();
        if (e.IsSuccess && e.HttpStatusCode is >= 200 and < 400)
        {
            CancelRetry();
            _recovery.MarkLoaded();
            _webReady = true;
            _connectionView.Visible = false;
            _webView.Visible = true;
            _webView.Focus();
            return;
        }
        HandleFailure(e.HttpStatusCode, e.WebErrorStatus);
    }

    void HandleFailure(int httpStatus, CoreWebView2WebErrorStatus error)
    {
        var failure = NavigationFailure.From(httpStatus, error);
        if (failure.IsCanceled && _recovery.PageLoaded) return;
        var delay = _recovery.NextDelay(failure);
        _lastDiagnostic = $"Windows {Application.ProductVersion.Split('+')[0]}\n"
            + $"时间：{DateTimeOffset.Now:yyyy-MM-dd HH:mm:ss zzz}\n"
            + $"HTTP：{httpStatus}\n连接状态：{error}\n自动重试：{_recovery.RetryCount}/{NavigationRecovery.MaximumRetries}";
        var status = delay.HasValue ? $"将在 {delay.Value} 秒后重试（{_recovery.RetryCount}/{NavigationRecovery.MaximumRetries}）"
            : _recovery.RetryCount >= NavigationRecovery.MaximumRetries
                ? "自动重试已结束，可以稍后重新连接。"
                : "未进行自动重试，可以处理连接问题后重新连接。";
        var message = delay.HasValue || !failure.CanRetry ? failure.Message
            : "连接尚未恢复。请检查网络或代理；持续发生时可查看诊断并联系支持。";
        _webView.Visible = false;
        _connectionView.ShowState(failure.Title, message, status, _lastDiagnostic, delay.HasValue);
        if (delay.HasValue)
        {
            _retryCancellation = new CancellationTokenSource();
            _ = RetryAfterAsync(delay.Value, _retryCancellation.Token);
        }
    }

    async Task RetryAfterAsync(int seconds, CancellationToken token)
    {
        try
        {
            for (var remaining = seconds; remaining > 0; remaining--)
            {
                if (IsDisposed || token.IsCancellationRequested) return;
                _connectionView.SetStatus($"将在 {remaining} 秒后重试（{_recovery.RetryCount}/{NavigationRecovery.MaximumRetries}）");
                await Task.Delay(1000, token);
            }
            if (!token.IsCancellationRequested && !IsDisposed) Connect(reset: false);
        }
        catch (OperationCanceledException) { }
    }

    void StopRecovery()
    {
        CancelRetry();
        CancelNavigation();
        _navigationId = null;
        _webView.CoreWebView2?.Stop();
        _connectionView.ShowState("连接已暂停", "已停止自动重试，可以随时重新连接。",
            $"已自动重试 {_recovery.RetryCount} 次", _lastDiagnostic, false);
    }

    async Task CheckDesktopUpdateAsync()
    {
        await Task.Delay(1200);
        if (!Uri.TryCreate(_startUrl, UriKind.Absolute, out var pageUri)) return;
        var baseUrl = $"{pageUri.Scheme}://{pageUri.Authority}";
        await DesktopUpdater.CheckAndOfferAsync(this, baseUrl);
    }

    void RegisterCaptureHotkey()
    {
        if (_hotkeyRegistered || !IsHandleCreated) return;
        // Ctrl+Shift+K：全局唤起「记」，对应手机三击音量加。
        _hotkeyRegistered = NativeMethods.RegisterHotKey(
            Handle,
            HotkeyIdCapture,
            NativeMethods.ModControl | NativeMethods.ModShift | NativeMethods.ModNorepeat,
            (int)Keys.K);
    }

    void UnregisterCaptureHotkey()
    {
        if (!_hotkeyRegistered || !IsHandleCreated) return;
        NativeMethods.UnregisterHotKey(Handle, HotkeyIdCapture);
        _hotkeyRegistered = false;
    }

    void BringToFrontSafe()
    {
        if (WindowState == FormWindowState.Minimized || NativeMethods.IsIconic(Handle))
        {
            NativeMethods.ShowWindow(Handle, NativeMethods.SwRestore);
            WindowState = FormWindowState.Normal;
        }
        Show();
        Activate();
        BringToFront();
        NativeMethods.SetForegroundWindow(Handle);
        _webView.Focus();
    }

    async Task OpenCaptureAsync()
    {
        if (_webView.CoreWebView2 is null) return;
        for (var i = 0; i < 20 && !_webReady; i++)
        {
            await Task.Delay(100);
        }
        try
        {
            await _webView.CoreWebView2.ExecuteScriptAsync(
                "(function(){try{if(typeof window.punchTimeLog==='function'){window.punchTimeLog(false);return;}if(typeof window.shuranOpenCapture==='function'){window.shuranOpenCapture();}}catch(e){}})();");
        }
        catch
        {
            /* page may still be loading */
        }
    }

    static void ShowRuntimeMissing()
    {
        MessageBox.Show(
            "需要先安装 Microsoft Edge WebView2 Runtime，再打开书然。\n\n" + WebView2RuntimeUrl,
            "书然",
            MessageBoxButtons.OK,
            MessageBoxIcon.Information);
    }
}
