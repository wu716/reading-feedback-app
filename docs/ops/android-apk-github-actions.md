# 用 GitHub Actions 打 Android 安装包

推荐使用 GitHub Actions 构建并发布签名 APK；也可在已配置 JDK、SDK 和签名文件的 Windows 机器运行 `mobile/android/build-apk.ps1`。APK 和签名文件均不得提交到 Git。签名文件已 gitignore：`mobile/android/keystore.properties`、`mobile/android/keystore/`。

## 仓库 Secrets（四个名字）

打开 https://github.com/wu716/reading-feedback-app/settings/secrets/actions 新增：

| 名字 | 值从哪来 |
|---|---|
| `KEYSTORE_BASE64` | 本机 `mobile/android/keystore/shuran.jks` 的 Base64 全文 |
| `KEYSTORE_PASSWORD` | `mobile/android/keystore.properties` 的 `storePassword` |
| `KEY_ALIAS` | `mobile/android/keystore.properties` 的 `keyAlias` |
| `KEY_PASSWORD` | `mobile/android/keystore.properties` 的 `keyPassword` |

在本机 PowerShell 生成 `KEYSTORE_BASE64` 并复制到剪贴板：

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("D:\projects\reading-feedback-app\mobile\android\keystore\shuran.jks")) | Set-Clipboard
```

不要把密码发到聊天里。不要把 `.jks`、`keystore.properties` 提交进 git。

## 工作流

- 文件：`.github/workflows/android-apk.yml`
- 名称：Build Android APK
- 触发：手动 Run workflow；以及 `main` 上 Android 相关文件变更
- 2.0 成功后的 Release 标签：`android-2.0`
- 2.0 下载地址：https://github.com/wu716/reading-feedback-app/releases/download/android-2.0/shuran.apk

## 放到生产机

登录后：

```bash
cd /opt/shuran-app && git pull --ff-only origin main
mkdir -p /opt/shuran-release-backups
cp -p /opt/shuran-app/releases/shuran.apk /opt/shuran-release-backups/shuran-before-2.0.apk
cp -p /opt/shuran-app/releases/shuran.apk.versioncode /opt/shuran-release-backups/shuran-before-2.0.apk.versioncode
curl -fL -o /opt/shuran-app/releases/shuran.apk.new https://github.com/wu716/reading-feedback-app/releases/download/android-2.0/shuran.apk
test -s /opt/shuran-app/releases/shuran.apk.new
sha256sum /opt/shuran-app/releases/shuran.apk.new
mv /opt/shuran-app/releases/shuran.apk.new /opt/shuran-app/releases/shuran.apk
printf '42\n' > /opt/shuran-app/releases/shuran.apk.versioncode
cd deploy/aliyun && docker compose up -d --build
```

目标文件：`/opt/shuran-app/releases/shuran.apk`，版本 2.0 / versionCode 42。下载前先核对 GitHub Release 的签名、版本和 SHA-256；部署后核对 `/health` 与 `/download/info`，并实际下载 APK 核对其包内版本。
