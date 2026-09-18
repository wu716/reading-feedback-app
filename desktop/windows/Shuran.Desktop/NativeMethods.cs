using System.Runtime.InteropServices;

namespace Shuran.Desktop;

static class NativeMethods
{
    public const int WmHotkey = 0x0312;
    public const int SwRestore = 9;
    public const int ModAlt = 0x0001;
    public const int ModControl = 0x0002;
    public const int ModShift = 0x0004;
    public const int ModNorepeat = 0x4000;

    public static readonly uint WmActivateShuran =
        RegisterWindowMessage("Shuran.Desktop.Activate");

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool RegisterHotKey(IntPtr hWnd, int id, int fsModifiers, int vk);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool UnregisterHotKey(IntPtr hWnd, int id);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern uint RegisterWindowMessage(string lpString);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool PostMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool IsIconic(IntPtr hWnd);

    public static void BroadcastActivate(bool openCapture)
    {
        PostMessage(
            new IntPtr(0xffff),
            WmActivateShuran,
            openCapture ? new IntPtr(1) : IntPtr.Zero,
            IntPtr.Zero);
    }
}
