# 安装 ffmpeg 指南

## 问题说明
Self-talk 模块的语音识别功能需要 `ffmpeg` 工具来处理音频格式转换。没有 `ffmpeg`，`pydub` 库无法将浏览器录制的音频转换为 Vosk 所需的格式。

## Windows 安装步骤

### 方法 1: 使用 Chocolatey (推荐)
1. 打开管理员权限的 CMD 或 PowerShell
2. 安装 Chocolatey (如果还没有安装):
   ```powershell
   Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
   ```
3. 安装 ffmpeg:
   ```powershell
   choco install ffmpeg
   ```

### 方法 2: 手动下载安装
1. 访问 https://ffmpeg.org/download.html
2. 点击 Windows 图标
3. 选择一个下载链接 (推荐 gyan.dev 或 BtbN)
4. 下载 `.zip` 文件
5. 解压到任意目录，比如 `D:\tools\ffmpeg` 或 `C:\Program Files\ffmpeg`
6. 将解压后的 `bin` 目录添加到系统 PATH 环境变量，比如 `D:\tools\ffmpeg\bin`:
   - 右键 "此电脑" → "属性" → "高级系统设置" → "环境变量"
   - 在 "系统变量" 中找到 `Path`，点击 "编辑"
   - 点击 "新建"，输入你解压的路径 + `\bin`，比如 `D:\tools\ffmpeg\bin`
   - 点击 "确定" 保存

### 方法 3: 使用 winget
```powershell
winget install ffmpeg
```

## 验证安装
安装完成后，打开新的 CMD 窗口，运行:
```cmd
ffmpeg -version
```

如果显示版本信息，说明安装成功。

## 注意事项
- 安装完成后需要重启终端或应用
- 确保 ffmpeg 在系统 PATH 中
- 如果使用虚拟环境，确保虚拟环境也能访问系统 PATH
