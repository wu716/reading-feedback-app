using System.Diagnostics;
using System.Net.Http.Json;
using System.Reflection;
using System.Text.Json;

namespace Shuran.Desktop;

static class DesktopUpdater
{
    const string UpdateArgument = "--apply-update=";
    const string UpdatePidArgument = "--update-pid=";
    static readonly HttpClient Client = new()
    {
        Timeout = TimeSpan.FromMinutes(3)
    };

    sealed record UpdateInfo(
        string? WindowsVersion,
        bool WindowsAvailable,
        string? WindowsDownloadUrl,
        long WindowsSizeBytes);

    public static bool TryApplyPendingUpdate(string[] args)
    {
        var updatePath = GetArgument(args, UpdateArgument);
        if (string.IsNullOrWhiteSpace(updatePath)) return false;

        var pid = ParsePid(GetArgument(args, UpdatePidArgument));
        if (pid > 0)
        {
            try
            {
                using var old = Process.GetProcessById(pid);
                old.WaitForExit(30_000);
            }
            catch (ArgumentException) { }
            catch (InvalidOperationException) { }
        }

        var target = Application.ExecutablePath;
        try
        {
            for (var i = 0; i < 30 && IsLocked(target); i++)
                Thread.Sleep(500);
            File.Copy(updatePath, target, true);
            File.Delete(updatePath);
            Process.Start(new ProcessStartInfo(target) { UseShellExecute = true });
            return true;
        }
        catch
        {
            // Keep the old executable if the install directory is read-only.
            return true;
        }
    }

    public static async Task CheckAndOfferAsync(Form owner, string baseUrl)
    {
        if (owner.IsDisposed || string.IsNullOrWhiteSpace(baseUrl)) return;
        try
        {
            var info = await Client.GetFromJsonAsync<UpdateInfo>(
                baseUrl.TrimEnd('/') + "/download/info",
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
            if (info is null || !info.WindowsAvailable || string.IsNullOrWhiteSpace(info.WindowsVersion)) return;

            var current = Assembly.GetEntryAssembly()?.GetName().Version?.ToString(3) ?? "0.0.0";
            if (!Version.TryParse(info.WindowsVersion, out var latest)
                || !Version.TryParse(current, out var installed)
                || latest <= installed)
                return;

            var answer = MessageBox.Show(
                owner,
                $"发现书然 Windows 新版本 {info.WindowsVersion}。\n\n现在下载并更新吗？\n更新过程中会自动重启书然。",
                "书然更新",
                MessageBoxButtons.YesNo,
                MessageBoxIcon.Information);
            if (answer != DialogResult.Yes) return;
            await DownloadAndRestartAsync(owner, baseUrl, info);
        }
        catch
        {
            // Updating is optional; a network failure must not block the app.
        }
    }

    static async Task DownloadAndRestartAsync(Form owner, string baseUrl, UpdateInfo info)
    {
        var url = string.IsNullOrWhiteSpace(info.WindowsDownloadUrl)
            ? baseUrl.TrimEnd('/') + "/download/windows"
            : info.WindowsDownloadUrl;
        if (url.StartsWith('/')) url = baseUrl.TrimEnd('/') + url;

        var directory = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Shuran", "updates");
        Directory.CreateDirectory(directory);
        var downloadPath = Path.Combine(directory, "shuran-windows.new.exe");
        using var response = await Client.GetAsync(url, HttpCompletionOption.ResponseHeadersRead);
        response.EnsureSuccessStatusCode();
        await using (var input = await response.Content.ReadAsStreamAsync())
        await using (var output = File.Create(downloadPath))
        {
            await input.CopyToAsync(output);
        }
        var expected = info.WindowsSizeBytes;
        if (new FileInfo(downloadPath).Length < 1_000_000
            || (expected > 0 && new FileInfo(downloadPath).Length != expected))
        {
            File.Delete(downloadPath);
            throw new InvalidDataException("Windows 安装包大小校验失败");
        }

        var currentPid = Environment.ProcessId;
        Process.Start(new ProcessStartInfo(Application.ExecutablePath)
        {
            UseShellExecute = true,
            Arguments = $"{UpdateArgument}\"{downloadPath}\" {UpdatePidArgument}{currentPid}"
        });
        owner.Close();
    }

    static bool IsLocked(string path)
    {
        try
        {
            using var stream = new FileStream(path, FileMode.Open, FileAccess.ReadWrite, FileShare.None);
            return false;
        }
        catch (IOException) { return true; }
        catch (UnauthorizedAccessException) { return true; }
    }

    static string? GetArgument(string[] args, string prefix) => args
        .FirstOrDefault(arg => arg.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))?[prefix.Length..]
        .Trim('"');

    static int ParsePid(string? value) => int.TryParse(value, out var pid) ? pid : 0;
}
