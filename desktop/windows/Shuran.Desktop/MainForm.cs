using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace Shuran.Desktop;

sealed class MainForm : Form
{
    const string WebView2RuntimeUrl = "https://go.microsoft.com/fwlink/p/?LinkId=2124703";
    const int HotkeyIdCapture = 1;
    readonly string _startUrl;
    readonly WebView2 _webView = new()
    {
        Dock = DockStyle.Fill,
        DefaultBackgroundColor = Color.White
    };
    bool _hotkeyRegistered;
    bool _webReady;

    public MainForm(string startUrl)
    {
        _startUrl = startUrl;
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
        Load += async (_, _) => await StartBrowserAsync();
        FormClosed += (_, _) => UnregisterCaptureHotkey();
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
            var userData = Path.Combine(
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
        _webView.CoreWebView2.Settings.UserAgent += " ShuranDesktop/1.6.0";
        _webView.CoreWebView2.NewWindowRequested += (_, e) =>
        {
            e.Handled = true;
            _webView.CoreWebView2.Navigate(e.Uri);
        };
        _webView.CoreWebView2.NavigationCompleted += (_, e) =>
        {
            if (e.IsSuccess)
            {
                _webReady = true;
            }
        };
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
        _webView.CoreWebView2.Navigate(_startUrl);
    }

    void RegisterCaptureHotkey()
    {
        if (_hotkeyRegistered || !IsHandleCreated) return;
        // Ctrl+Shift+K：全局唤起「记」，对应手机三击音量减。
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
