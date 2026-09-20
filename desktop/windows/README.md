# 书然 Windows 桌面壳

薄原生窗口，用 WebView2 打开现有网站。不是第二套前端。

坐下工作时用这个；出门用手机看日程、「记」、偶尔 Self-talk。

## 为什么清晰

窗口按 **PerMonitorV2** DPI 感知，WebView 按显示器像素排版。荣耀电脑管家套 APK 会把安卓界面当位图放大，全屏必糊。

## 本版能力（1.6.1）

- 双击打开，任务栏常驻；再开一次会唤起已有窗口，不会叠多个。
- **Ctrl+Shift+K** 全局唤起「记」（对应手机三击音量减）。窗口内也可用 **Ctrl+K**。
- 命令行加 `--capture` 可直接打开「记」。

## 依赖

- Windows 10/11
- [Microsoft Edge WebView2 Runtime](https://go.microsoft.com/fwlink/p/?LinkId=2124703)（Win11 通常已有）

构建产物包含 .NET 运行时，内测用户不需要另装 .NET。

## 本机编译

```powershell
cd D:\projects\reading-feedback-app\desktop\windows
.\build.ps1
```

成功后生成以下两个文件（都不要提交 git）：

- `releases/shuran-windows.exe`：服务器下载页使用
- `releases/shuran-windows-1.6.1.zip`：可直接通过微信发送给内测用户

这是未签名的内测版本，仅发送给受邀测试用户。Windows 可能显示未知发布者提示；正式公开发布时再使用 MSIX 和可信签名。

上传服务器：

```powershell
scp .\releases\shuran-windows.exe ubuntu@43.161.238.165:/opt/shuran-app/releases/shuran-windows.exe
```

## 打开

双击 `shuran-windows.exe`。默认打开 `http://43.161.238.165:8000`。

换地址任选其一：

- 启动参数：`.\shuran-windows.exe --url=http://127.0.0.1:8000`
- 环境变量 `SHURAN_URL`
- 同目录或 `%LocalAppData%\Shuran\start-url.txt` 里写一行网址

标准标题栏，可用 Win+← / Win+→ 吸附。
