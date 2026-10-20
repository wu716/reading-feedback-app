#!/usr/bin/env bash
# Run as root on the production host after pulling origin/main.
set -euo pipefail
cd /opt/shuran-app
version_name=2.0.11
version_code=53
backup_dir=/opt/shuran-release-backups
mkdir -p "$backup_dir"
work_dir=$(mktemp -d "$backup_dir/upgrade-2.0.11.XXXXXX")
apk_new="$work_dir/shuran.apk"
release_json="$work_dir/release.json"
curl -fsSL -o "$release_json" \
  "https://api.github.com/repos/wu716/reading-feedback-app/releases/tags/android-${version_name}"
expected_sha=$(python3 - "$release_json" "$version_name" "$version_code" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as fh:
    release = json.load(fh)
expected = f"Android {sys.argv[2]} (versionCode {sys.argv[3]})"
if release.get("name") != expected:
    raise SystemExit(f"Release title must be {expected}")
assets = [a for a in release.get("assets", []) if a.get("name") == "shuran.apk"]
if len(assets) != 1 or not str(assets[0].get("digest", "")).startswith("sha256:"):
    raise SystemExit("Release APK or SHA-256 digest is missing")
print(assets[0]["digest"].removeprefix("sha256:"))
PY
)
curl -fL -o "$apk_new" \
  "https://github.com/wu716/reading-feedback-app/releases/download/android-${version_name}/shuran.apk"
printf '%s  %s\n' "$expected_sha" "$apk_new" | sha256sum --check -
python3 - "$apk_new" "$version_name" "$version_code" <<'PY'
import json
import sys
from pathlib import Path
from app.apk_version import read_apk_version
with open("releases/latest.json", encoding="utf-8") as fh:
    meta = json.load(fh)
if (meta.get("versionCode"), meta.get("versionName")) != (int(sys.argv[3]), sys.argv[2]):
    raise SystemExit("Download metadata is not ready for this release")
if read_apk_version(Path(sys.argv[1])) != (int(sys.argv[3]), sys.argv[2]):
    raise SystemExit("APK manifest does not match this release")
PY
stamp=$(date +%Y%m%d-%H%M%S)
if [ -f releases/shuran.apk ]; then
  cp -p releases/shuran.apk "$backup_dir/shuran-${stamp}.apk"
fi
if [ -f releases/shuran.apk.versioncode ]; then
  cp -p releases/shuran.apk.versioncode "$backup_dir/shuran-${stamp}.apk.versioncode"
fi
(cd deploy/aliyun && docker compose exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"') > "$work_dir/database.sql"
test -s "$work_dir/database.sql"
cp "$apk_new" releases/shuran.apk.new
mv releases/shuran.apk.new releases/shuran.apk
printf '%s\n' "$version_code" > releases/shuran.apk.versioncode
cd deploy/aliyun
docker compose up -d --build
curl --retry 20 --retry-delay 3 --retry-connrefused -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/download/info | python3 -c '
import json, sys
info = json.load(sys.stdin)
print(json.dumps(info, ensure_ascii=False, indent=2))
assert info.get("available") is True, "APK is unavailable"
assert info.get("versionCode") == 53 and info.get("versionName") == "2.0.11", "Download version mismatch"
'
printf '\nDeployment verified. Backup directory: %s\n' "$work_dir"
