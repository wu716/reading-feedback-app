namespace Shuran.Desktop;

static class Program
{
    public const string DefaultUrl = "http://43.161.238.165:8000/?v=20260917upd1";

    [STAThread]
    static void Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);
        Application.Run(new MainForm(ResolveStartUrl(args)));
    }

    static string ResolveStartUrl(string[] args)
    {
        foreach (var arg in args)
        {
            if (arg.StartsWith("--url=", StringComparison.OrdinalIgnoreCase))
            {
                var value = arg["--url=".Length..].Trim();
                if (LooksLikeUrl(value)) return value;
            }
        }

        var fromEnv = Environment.GetEnvironmentVariable("SHURAN_URL");
        if (LooksLikeUrl(fromEnv)) return fromEnv!.Trim();

        foreach (var path in ConfigFileCandidates())
        {
            if (!File.Exists(path)) continue;
            var line = File.ReadLines(path).FirstOrDefault(static x => !string.IsNullOrWhiteSpace(x))?.Trim();
            if (LooksLikeUrl(line)) return line!;
        }

        return DefaultUrl;
    }

    static IEnumerable<string> ConfigFileCandidates()
    {
        yield return Path.Combine(AppContext.BaseDirectory, "start-url.txt");
        yield return Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Shuran",
            "start-url.txt");
    }

    static bool LooksLikeUrl(string? value) =>
        !string.IsNullOrWhiteSpace(value)
        && (value.StartsWith("http://", StringComparison.OrdinalIgnoreCase)
            || value.StartsWith("https://", StringComparison.OrdinalIgnoreCase));
}
