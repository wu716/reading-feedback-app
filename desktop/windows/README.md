# 书然 Windows 桌面壳

薄原生窗口，用 WebView2 打开现有网站。不是第二套前端。

坐下工作时用这个；出门用手机看日程、「记」、偶尔 Self-talk。

## 为什么清晰

窗口按 **PerMonitorV2** DPI 感知，WebView 按显示器像素排版。荣耀电脑管家套 APK 会把安卓界面当位图放大，全屏必糊。

## 本版能力（1.6.4）

- 双击打开，任务栏常驻；再开一次会唤起已有窗口，不会叠多个。
- **Ctrl+Shift+K** 全局唤起「记」（对应手机三击音量加）。窗口内也可用 **Ctrl+K**。
- 命令行加 `--capture` 可直接打开「记」。
- 界面语言跟随网页端设置，可在「我的 → 语言」切换中文 / English。
- 启动时自动检查桌面版本；确认后下载新版，自动重启并替换旧程序。
- 首次连接的临时网络错误及 HTTP 408/502/503/504，分别等待约 2、5、10 秒后重试，最多三次；单次连接等待最多 15 秒。
- 失败界面由本地 Windows 控件提供，网页打不开时也能重新连接、停止自动重试及查看简短诊断；证书、验证与其他 HTTP 错误不盲目重试。
- 仅自动重试客户端发起的首页 GET；已经打开的页面、表单与保存操作不自动重放，不修改系统代理。
- 更新元数据通过明确的 snake_case 字段映射读取；1.6.3 的旧更新器不能靠服务器更新获得这项修复，需要手动下载 1.6.4。

## 依赖

- Windows 10/11
- [Microsoft Edge WebView2 Runtime](https://go.microsoft.com/fwlink/p/?LinkId=2124703)（Win11 通常已有）

构建产物包含 .NET 运行时，内测用户不需要另装 .NET。

## 本机编译

```powershell
cd D:\projects\reading-feedback-app\desktop\windows
.\build.ps1
```

正在使用本地 `releases/shuran-windows.exe` 时，构建到检查资料目录，保留原程序：

```powershell
cd D:\projects\reading-feedback-app
.\desktop\windows\build.ps1 -OutputDirectory D:\UserData\ProjectArtifacts\reading-feedback-app\windows-1.6.4-final
```

成功后生成以下两个文件（都不要提交 git）：

- `releases/shuran-windows.exe`：服务器下载页使用
- `releases/shuran-windows-1.6.4.zip`：可直接通过微信发送给内测用户

同时生成 `windows-latest.json`，包含实际安装包的版本、长度及 SHA-256。发布时将该元数据纳入源码提交，EXE/ZIP 不提交 Git；服务器上元数据与 EXE 一致后才提供 Windows 下载及更新。

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
