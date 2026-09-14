using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace Shuran.Desktop;

sealed class MainForm : Form
{
    const string WebView2RuntimeUrl = "https://go.microsoft.com/fwlink/p/?LinkId=2124703";
    readonly string _startUrl;
    readonly WebView2 _webView = new()
    {
        Dock = DockStyle.Fill,
        DefaultBackgroundColor = Color.White
    };

    public MainForm(string startUrl)
    {
        _startUrl = startUrl;
        Text = "书然";
        Width = 1100;
        Height = 760;
        MinimumSize = new Size(420, 560);
        StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.Sizable;
        AutoScaleMode = AutoScaleMode.Dpi;
        KeyPreview = true;
        Controls.Add(_webView);
        Load += async (_, _) => await StartBrowserAsync();
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
        _webView.CoreWebView2.Settings.UserAgent += " ShuranDesktop/1.5.0";
        _webView.CoreWebView2.NewWindowRequested += (_, e) =>
        {
            e.Handled = true;
            _webView.CoreWebView2.Navigate(e.Uri);
        };
        _webView.CoreWebView2.Navigate(_startUrl);
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
