using System.Text.Json;
using Microsoft.Toolkit.Uwp.Notifications;

namespace Shuran.Desktop;

/// <summary>Native clock survives hidden/minimized WebView pages; never starts unattended work.</summary>
sealed class FocusReminders : IDisposable
{
    readonly System.Windows.Forms.Timer _clock = new() { Interval = 500 };
    readonly HashSet<string> _delivered = new();
    readonly Action _openExecution;
    int _id;
    string _kind = "";
    long _deadline;
    int _breakMinutes = 5;
    long _serverDeadline;
    readonly string _soundPath;
    readonly System.Media.SoundPlayer _player;

    public FocusReminders(Action openExecution)
    {
        _openExecution = openExecution;
        var folder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Shuran", "Sounds");
        Directory.CreateDirectory(folder);
        _soundPath = Path.Combine(folder, "focus-falling-pluck.wav");
        using var source = typeof(FocusReminders).Assembly.GetManifestResourceStream("FocusChime.wav");
        if (source is not null) { using var file = File.Create(_soundPath); source.CopyTo(file); }
        _player = new System.Media.SoundPlayer(_soundPath);
        ToastNotificationManagerCompat.OnActivated += OnActivated;
        _clock.Tick += (_, _) => Tick();
        _clock.Start();
    }

    void OnActivated(ToastNotificationActivatedEventArgsCompat args) => _openExecution();

    public void Sync(JsonElement data)
    {
        Tick(); // Deliver an elapsed alarm before the page replaces it with the automatic break.
        if (data.TryGetProperty("completed", out var complete) && complete.GetBoolean()) return;
        if (!data.TryGetProperty("id", out var id) || !data.TryGetProperty("deadline_ms", out var at))
        { _id = 0; _kind = ""; return; }
        var deadline = at.GetInt64();
        var kind = data.GetProperty("kind").GetString() ?? "";
        if (kind is not ("work" or "break")) return;
        if (deadline > DateTimeOffset.UtcNow.AddMinutes(181).ToUnixTimeMilliseconds()) return;
        _id = id.GetInt32(); _deadline = deadline; _kind = kind;
        _serverDeadline = data.TryGetProperty("server_deadline_ms", out var serverAt) ? serverAt.GetInt64() : deadline;
        _breakMinutes = data.TryGetProperty("break_minutes", out var rest) ? Math.Clamp(rest.GetInt32(), 1, 180) : 5;
        Tick();
    }

    void Tick()
    {
        var now = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
        if (_id == 0 || now < _deadline) return;
        if (_kind == "work")
        {
            var restEnd = _deadline + _breakMinutes * 60_000L;
            if (now < restEnd) Show("工作片结束，休息 " + _breakMinutes + " 分钟",
                "休息已自动开始。先不看手机，也不查看消息。站起来走走，让眼睛离开屏幕。", "work:" + _serverDeadline);
            _kind = "break"; _deadline = restEnd; _serverDeadline += _breakMinutes * 60_000L;
        }
        if (_kind == "break" && now >= _deadline)
        {
            // ExpirationTime also avoids stale reminders after long sleep.
            if (now - _deadline < 6 * 3600_000L) Show("休息结束，准备好再开始", "准备好后开始下一项；当前未计工作时间。", "break:" + _serverDeadline);
            _id = 0;
        }
    }

    void Show(string title, string body, string key)
    {
        if (_delivered.Contains(key)) return;
        try
        {
            new ToastContentBuilder().AddArgument("view", "execution").AddText(title).AddText(body)
                .AddAudio(new ToastAudio { Silent = true })
                .Show(toast => { toast.Tag = "focus"; toast.Group = "execution"; toast.ExpirationTime = DateTimeOffset.Now.AddHours(6); });
            _delivered.Add(key);
            // Unpackaged apps cannot use a file URI as toast audio. Play the embedded
            // reviewed sound once, without the system's additional default chime.
            if (ToastNotificationManagerCompat.CreateToastNotifier().Setting == Windows.UI.Notifications.NotificationSetting.Enabled)
                _player.Play();
        }
        catch (Exception ex) { System.Diagnostics.Trace.WriteLine("Focus notification: " + ex.Message); }
    }

    public void Dispose()
    {
        _clock.Stop(); _clock.Dispose();
        _player.Dispose();
        ToastNotificationManagerCompat.OnActivated -= OnActivated;
    }
}
