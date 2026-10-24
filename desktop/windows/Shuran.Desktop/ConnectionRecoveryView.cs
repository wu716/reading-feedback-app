namespace Shuran.Desktop;

internal sealed class ConnectionRecoveryView : Panel
{
    readonly FlowLayoutPanel _content = new()
    {
        AutoSize = true, FlowDirection = FlowDirection.TopDown, WrapContents = false,
        Location = new Point(0, 0), Padding = new Padding(32), Margin = Padding.Empty
    };
    readonly Label _title = new() { AutoSize = true, Margin = new Padding(0, 12, 0, 12) };
    readonly Label _message = new() { AutoSize = true, Margin = new Padding(0, 0, 0, 12) };
    readonly Label _status = new() { AutoSize = true, Margin = new Padding(0, 0, 0, 20) };
    readonly FlowLayoutPanel _actions = new() { AutoSize = true, WrapContents = true, Margin = Padding.Empty };
    readonly Button _retry = MakeButton("重新连接", true);
    readonly Button _stop = MakeButton("停止自动重试");
    readonly Button _details = MakeButton("查看诊断");
    readonly Label _diagnostic = new() { AutoSize = true, Visible = false, Margin = new Padding(0, 20, 0, 0) };

    public event Action? RetryRequested;
    public event Action? StopRequested;

    public ConnectionRecoveryView()
    {
        Name = "ConnectionRecovery";
        AccessibleName = "书然连接恢复";
        Dock = DockStyle.Fill;
        AutoScroll = true;
        BackColor = Color.FromArgb(250, 250, 248);
        ForeColor = Color.FromArgb(37, 55, 70);
        Font = new Font("Microsoft YaHei UI", 11);
        _title.Font = new Font(Font.FontFamily, 20, FontStyle.Bold);
        _status.ForeColor = Color.FromArgb(72, 99, 118);
        _diagnostic.Font = new Font("Microsoft YaHei UI", 10);
        var brand = new Label
        {
            Text = "书然", AutoSize = true, Font = new Font("SimSun", 24),
            ForeColor = Color.FromArgb(54, 94, 118), Margin = new Padding(0, 12, 0, 12)
        };
        _retry.Click += (_, _) => RetryRequested?.Invoke();
        _stop.Click += (_, _) => StopRequested?.Invoke();
        _details.Click += (_, _) =>
        {
            _diagnostic.Visible = !_diagnostic.Visible;
            _details.Text = _diagnostic.Visible ? "收起诊断" : "查看诊断";
        };
        _actions.Controls.AddRange([_retry, _stop, _details]);
        _content.Controls.AddRange([brand, _title, _message, _status, _actions, _diagnostic]);
        Controls.Add(_content);
        Resize += (_, _) => FitContent();
        FitContent();
    }

    static Button MakeButton(string text, bool primary = false) => new()
    {
        Text = text, AutoSize = true, MinimumSize = new Size(112, 44),
        Padding = new Padding(10, 5, 10, 5), Margin = new Padding(0, 0, 10, 10),
        FlatStyle = FlatStyle.Flat, UseVisualStyleBackColor = false,
        BackColor = primary ? Color.FromArgb(54, 94, 118) : Color.FromArgb(234, 240, 244),
        ForeColor = primary ? Color.White : Color.FromArgb(41, 75, 99),
        FlatAppearance = { BorderColor = Color.FromArgb(140, 163, 180), BorderSize = 1 }
    };

    void FitContent()
    {
        var width = Math.Max(180, Math.Min(660, ClientSize.Width - 64));
        foreach (var label in new[] { _title, _message, _status, _diagnostic })
            label.MaximumSize = new Size(width, 0);
        _actions.MaximumSize = new Size(width, 0);
        _content.MaximumSize = new Size(width + 64, 0);
    }

    public void ShowState(string title, string message, string status, string diagnostic, bool canStop)
    {
        _title.Text = title;
        _message.Text = message;
        _status.Text = status;
        _diagnostic.Text = diagnostic;
        _stop.Visible = canStop;
        Visible = true;
        BringToFront();
    }

    public void SetStatus(string text) => _status.Text = text;
}
