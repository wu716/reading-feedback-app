# 用 GitHub Actions 打 Android 安装包

本机 Windows 不保存、不编译 `*.apk`。签名文件已 gitignore：`mobile/android/keystore.properties`、`mobile/android/keystore/`。

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
- 成功后 Release 标签：`android-{versionName}`（Gradle 当前是 1.5.4）
- 线上现在能装的包是已发布的 `android-1.5.2`。`android-1.5.4` 还没有 Release，因为 Actions 缺少签名 Secrets；不要 curl 这个不存在的地址，会把 `Not Found` 存成假 APK。

当前可下载：https://github.com/wu716/reading-feedback-app/releases/download/android-1.5.2/shuran.apk

## 放到生产机

登录后：

```bash
cd /opt/shuran-app && git pull origin main && mkdir -p /opt/shuran-app/releases && rm -f /opt/shuran-app/releases/shuran.apk && curl -L -o /opt/shuran-app/releases/shuran.apk https://github.com/wu716/reading-feedback-app/releases/download/android-1.5.2/shuran.apk && ls -l /opt/shuran-app/releases/shuran.apk && cd deploy/aliyun && docker compose up -d --build
```

目标文件：`/opt/shuran-app/releases/shuran.apk`，应约为 1.8MB（1810063 字节），版本 1.5.2 / versionCode 18。若只有几字节，说明又下到了 404 文本，不要拿去安装。
