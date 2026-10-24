#!/usr/bin/env bash
# Run as root after deploying this source version. Installs only the verified APK.
set -euo pipefail
cd /opt/shuran-app
version_name=2.0.26
version_code=68
expected_sha=0f3ceddfeaec5bf45836d9e513ff4c989321c9b8b41ddbb1bfdf00192ee23833
backup_dir=/opt/shuran-release-backups
mkdir -p "$backup_dir"
work_dir=$(mktemp -d "$backup_dir/apk-2.0.26.XXXXXX")
apk_new="$work_dir/shuran.apk"
curl --retry 3 -fL -o "$apk_new" \
  "https://github.com/wu716/reading-feedback-app/releases/download/android-${version_name}/shuran.apk"
printf '%s  %s\n' "$expected_sha" "$apk_new" | sha256sum --check -
python3 - "$apk_new" "$version_name" "$version_code" <<'PY'
import json
import sys
from pathlib import Path
from app.apk_version import read_apk_version
expected = (int(sys.argv[3]), sys.argv[2])
meta = json.loads(Path("releases/latest.json").read_text(encoding="utf-8"))
if (meta.get("versionCode"), meta.get("versionName")) != expected:
    raise SystemExit("Download metadata does not match this release")
if read_apk_version(Path(sys.argv[1])) != expected:
    raise SystemExit("APK manifest does not match this release")
PY
if [ -f releases/shuran.apk ]; then
  cp -p releases/shuran.apk "$work_dir/previous.apk"
fi
if [ -f releases/shuran.apk.versioncode ]; then
  cp -p releases/shuran.apk.versioncode "$work_dir/previous.apk.versioncode"
fi
cp "$apk_new" releases/shuran.apk.new
mv releases/shuran.apk.new releases/shuran.apk
printf '%s\n' "$version_code" > releases/shuran.apk.versioncode
curl --retry 10 --retry-delay 3 --retry-connrefused -fsS \
  http://127.0.0.1:8000/download/info | python3 -c '
import json, sys
info = json.load(sys.stdin)
print(json.dumps(info, ensure_ascii=False, indent=2))
assert info.get("available") is True, "APK is unavailable"
assert (info.get("versionCode"), info.get("versionName")) == (68, "2.0.26"), "Download version mismatch"
'
printf '\nAPK installed. Previous package and verification files: %s\n' "$work_dir"
