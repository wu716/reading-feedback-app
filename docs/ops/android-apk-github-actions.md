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
- Release 标签由 `mobile/android/app/build.gradle` 的 `versionName` 生成，例如 `2.0.8` 对应 `android-2.0.8`
- 只有 Actions 成功、Release 中存在 `shuran.apk`，且 Release 标题的 `versionCode` 与源码一致后，才能更新服务器安装包和 `releases/latest.json`

## 放到生产机

先在 GitHub 核对目标 Release 和签名构建日志。以下命令对应已发布的 `2.0.14` / `versionCode 56`；Release 给出的 APK SHA-256 为 `91fefb563d44492d51ff1e379df3d23b8b74b46b1ec2be84e41e5cdd092d881f`。下载或校验失败时不会替换服务器现有安装包。复制命令时不要复制 Markdown 的代码围栏（```）。

Windows PowerShell 登录：

```powershell
ssh ubuntu@43.161.238.165
```

Ubuntu 登录后先取得管理员权限：

```bash
sudo -i
```

再执行以下整段命令：

```bash
bash <<'SH'
set -euo pipefail
version_name=2.0.14
version_code=56
cd /opt/shuran-app
apk=releases/shuran.apk
apk_new=releases/shuran.apk.new
verify_apk=$(mktemp /tmp/shuran-download-XXXXXX.apk)
trap 'rm -f "$apk_new" "$verify_apk"' EXIT
curl --retry 3 -fL -o "$apk_new" "https://github.com/wu716/reading-feedback-app/releases/download/android-${version_name}/shuran.apk"
test -s "$apk_new"
printf '%s  %s\n' '91fefb563d44492d51ff1e379df3d23b8b74b46b1ec2be84e41e5cdd092d881f' "$apk_new" | sha256sum --check -
mkdir -p /opt/shuran-release-backups
stamp=$(date +%Y%m%d-%H%M%S)
backup="/opt/shuran-release-backups/shuran-${stamp}.apk"
if [ -f "$apk" ]; then cp -p "$apk" "$backup"; fi
if [ -f "$apk.versioncode" ]; then cp -p "$apk.versioncode" "$backup.versioncode"; fi
# 旧版仓库跟踪了 versioncode=23；只恢复这一个已备份的生成文件，避免它阻止 git pull。
if git ls-files --error-unmatch -- "$apk.versioncode" >/dev/null 2>&1; then
  git restore --staged --worktree -- "$apk.versioncode"
fi
git pull --ff-only origin main
python3 - "$apk_new" "$version_name" "$version_code" <<'PY'
import json
import sys
from pathlib import Path
from app.apk_version import read_apk_version

with open("releases/latest.json", encoding="utf-8") as fh:
    metadata = json.load(fh)
if metadata.get("versionName") != sys.argv[2] or metadata.get("versionCode") != int(sys.argv[3]):
    raise SystemExit("releases/latest.json has not been updated for this APK")
if read_apk_version(Path(sys.argv[1])) != (int(sys.argv[3]), sys.argv[2]):
    raise SystemExit("APK manifest does not match the published version")
PY
mv "$apk_new" "$apk"
printf '%s\n' "$version_code" > "$apk.versioncode"
cd deploy/aliyun
docker compose up -d --build
curl --retry 12 --retry-delay 2 --retry-connrefused -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/download/info | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("available") is True and d.get("versionCode")==56 and d.get("versionName")=="2.0.14", d; print("APK_READY", d["versionName"], d["versionCode"])'
curl -fsS http://127.0.0.1:8000/download/apk -o "$verify_apk"
printf '%s  %s\n' '91fefb563d44492d51ff1e379df3d23b8b74b46b1ec2be84e41e5cdd092d881f' "$verify_apk" | sha256sum --check -
SH
```

最后确认 `/download/info` 的 `available` 为 `true`、`versionCode` 为 `56`、`versionName` 为 `2.0.14`，且实际下载 APK 的哈希与 Release 一致。以后发布新版本时，先核对新 Release，再替换脚本中的版本号和固定 SHA-256。
