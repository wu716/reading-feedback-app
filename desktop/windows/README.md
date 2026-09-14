# 书然 Windows 桌面壳

薄原生窗口，用 WebView2 打开现有网站。不是第二套前端。

## 为什么清晰

窗口按 **PerMonitorV2** DPI 感知，WebView 按显示器像素排版。荣耀电脑管家套 APK 会把安卓界面当位图放大，全屏必糊。

## 依赖

- Windows 10/11
- [.NET 9 Desktop Runtime](https://dotnet.microsoft.com/download/dotnet/9.0)（本机已装 SDK 则可直接跑）
- [Microsoft Edge WebView2 Runtime](https://go.microsoft.com/fwlink/p/?LinkId=2124703)（Win11 通常已有）

## 本机编译

```powershell
cd D:\projects\reading-feedback-app\desktop\windows
.\build.ps1
```

成功后生成 `releases/shuran-windows.exe`（不要提交 git）。

## 打开

双击 `shuran-windows.exe`。默认打开 `http://47.236.122.207:8000`。

换地址任选其一：

- 启动参数：`.\shuran-windows.exe --url=http://127.0.0.1:8000`
- 环境变量 `SHURAN_URL`
- 同目录或 `%LocalAppData%\Shuran\start-url.txt` 里写一行网址

标准标题栏，可用 Win+← / Win+→ 吸附。
