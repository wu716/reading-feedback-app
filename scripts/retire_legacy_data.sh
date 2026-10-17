#!/usr/bin/env bash
# Remove retired Shuran data only after the corresponding write routes are gone.
# Usage: bash retire_legacy_data.sh preview | delete
set -euo pipefail

mode="${1:-preview}"
case "$mode" in
  preview|delete) ;;
  *) echo "用法：bash retire_legacy_data.sh preview|delete" >&2; exit 2 ;;
esac

repo=/opt/shuran-app
deploy="$repo/deploy/aliyun"
cd "$repo"

old_route_pattern='app\.include_router\((ebooks|dashboard|actions|practice|ai_advice|self_talk_router|self_talk_reminders_router|habit_programs|methods)(\.router)?'

echo "=== 书然代码版本 ==="
git -c safe.directory="$repo" log -1 --format='%h %s'
git -c safe.directory="$repo" status --short

if [[ "$mode" == preview ]]; then
  echo "=== 旧板块路由注册 ==="
  grep -nE "$old_route_pattern" main.py || true
  cd "$deploy"
  echo "=== 容器 ==="
  docker compose ps
  echo "=== 全部业务表行数（只读） ==="
  docker compose exec -T db sh -c 'exec psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' <<'SQL'
\pset pager off
SELECT format('SELECT %L AS table_name, count(*)::bigint AS row_count FROM %I.%I;',
              table_name, table_schema, table_name)
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
ORDER BY table_name
\gexec
SELECT reminder_type, count(*)::bigint AS row_count
FROM self_talk_reminder_logs GROUP BY reminder_type ORDER BY reminder_type;
SELECT kind, count(*)::bigint AS row_count
FROM ai_call_logs GROUP BY kind ORDER BY kind;
SELECT count(*)::bigint AS daily_tasks_linked_to_actions
FROM daily_tasks WHERE action_id IS NOT NULL;
SQL
  echo "=== 书然上传目录：仅数量和大小，不列文件名 ==="
  docker compose exec -T app python - <<'PY'
from pathlib import Path

root = Path('/app/uploads')
for name in ('ebooks', 'self_talks'):
    folder = root / name
    files = [p for p in folder.rglob('*') if p.is_file() and not p.is_symlink()] if folder.is_dir() else []
    print(f'{name}: {len(files)} files, {sum(p.stat().st_size for p in files)} bytes')
PY
  exit 0
fi

# The current production version still has these routes. Never bypass this check.
if grep -Eq "$old_route_pattern" main.py; then
  echo "已停止：源码仍注册旧板块路由。先部署完成代码退出的版本。" >&2
  exit 3
fi

# Singapore backfill staging includes copies of both retired and retained data.
# It must be verified and retired separately before active-data deletion.
cd "$deploy"
staging_count="$(docker compose exec -T db sh -c 'exec psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -v ON_ERROR_STOP=1' <<'SQL'
SELECT count(*) FROM pg_tables
WHERE schemaname = 'public'
  AND (tablename LIKE 'sg_stg_%' OR tablename = 'sg_id_map');
SQL
)"
if [[ "${staging_count//[[:space:]]/}" != 0 ]]; then
  echo "已停止：仍有新加坡补迁暂存表（${staging_count//[[:space:]]/} 张），其中含需要保留的账户和日程数据。先核验补迁，再单独清理暂存表。" >&2
  exit 4
fi
docker compose exec -T app python - <<'PY'
from main import app

paths = [route.path for route in app.routes]
old_prefixes = (
    '/api/actions', '/api/practice', '/api/ai-advice',
    '/api/self_talks', '/api/self_talk_reminders',
    '/api/habit', '/api/methods', '/api/ebooks',
    '/api/dashboard', '/api/stats',
)
found = [path for path in paths if path.startswith(old_prefixes)]
if found:
    raise SystemExit('已停止：运行中的容器仍开放旧接口，例如 ' + ', '.join(found[:5]))
PY

test -n "$(docker compose ps --status running -q app)" || {
  echo "已停止：书然 app 容器未运行。" >&2
  exit 3
}

backup_dir=/root/shuran-cleanup-backups
mkdir -p "$backup_dir"
stamp="$(date +%Y%m%d-%H%M%S)-$$"
db_backup="$backup_dir/shuran-$stamp.dump"
upload_backup="$backup_dir/uploads-$stamp.tar"

docker compose stop app
restart_app() { docker compose start app >/dev/null || true; }
trap restart_app EXIT

docker compose exec -T db sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$db_backup"
test -s "$db_backup"
docker compose exec -T db pg_restore -l < "$db_backup" > /dev/null

docker compose run --rm --no-deps --entrypoint python app -c \
  'import sys,tarfile; t=tarfile.open(fileobj=sys.stdout.buffer,mode="w|"); t.add("/app/uploads",arcname="uploads"); t.close()' \
  > "$upload_backup"
test -s "$upload_backup"
tar -tf "$upload_backup" > /dev/null
echo "已验证数据库备份：$db_backup"
echo "已验证上传文件备份：$upload_backup"

docker compose exec -T db sh -c 'exec psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' <<'SQL'
BEGIN;

CREATE TEMP TABLE protected_before (name text PRIMARY KEY, n bigint);
DO $check$
DECLARE item text; total bigint;
BEGIN
  FOREACH item IN ARRAY ARRAY[
    'users','subscriptions','invite_codes','auth_codes',
    'daily_todos','daily_tasks','daily_schedules',
    'future_actions','ideas','time_log_nodes','goals','projects',
    'project_stages','project_tasks','task_dependencies',
    'task_checklist_items','work_sessions',
    'time_activity_assessments','process_templates','audit_logs',
    'self_talk_reminder_settings'
  ] LOOP
    EXECUTE format('SELECT count(*) FROM %I', item) INTO total;
    INSERT INTO protected_before VALUES (item, total);
  END LOOP;
END $check$;

CREATE TEMP TABLE protected_todo_reminders AS
SELECT count(*)::bigint AS n FROM self_talk_reminder_logs WHERE reminder_type = 'todo';
CREATE TEMP TABLE protected_profiles AS
SELECT count(*)::bigint AS n FROM anonymized_data WHERE data_type = 'user_profile';

DELETE FROM method_uses;
DELETE FROM method_cards;
DELETE FROM method_visits;
DELETE FROM product_feedback;

DELETE FROM ai_advice_messages;
DELETE FROM ai_advice_sessions;
DELETE FROM ai_call_logs;

DELETE FROM self_talk_playback_logs;
DELETE FROM self_talks;
DELETE FROM self_talk_reminder_logs WHERE reminder_type IS DISTINCT FROM 'todo';
-- These settings also control todo reminders. Keep the shared row and clear
-- only retired behavior settings.
UPDATE self_talk_reminder_settings
SET daily_reminder_enabled = false,
    daily_reminder_time = NULL,
    after_action_reminder = false,
    after_new_action_reminder = false,
    inactive_days_threshold = 0,
    reading_reminder_enabled = false,
    reading_reminder_time = NULL;

DELETE FROM habit_events;
DELETE FROM habit_programs;
DELETE FROM practice_logs;
DELETE FROM anonymized_data WHERE data_type IN ('actions', 'practice_logs');
-- Keep daily tasks; disconnect their old action reference only.
UPDATE daily_tasks SET action_id = NULL WHERE action_id IS NOT NULL;
DELETE FROM actions;

DELETE FROM reading_entries;
DELETE FROM ebook_progress;
DELETE FROM ebook_notes;
DELETE FROM ebook_chapters;
DELETE FROM ebooks;

DO $check$
DECLARE row_before record; total bigint;
BEGIN
  FOR row_before IN SELECT * FROM protected_before LOOP
    EXECUTE format('SELECT count(*) FROM %I', row_before.name) INTO total;
    IF total <> row_before.n THEN
      RAISE EXCEPTION '保留表 % 行数变化：% -> %',
        row_before.name, row_before.n, total;
    END IF;
  END LOOP;
END $check$;

DO $check$
BEGIN
  IF (SELECT count(*) FROM self_talk_reminder_logs WHERE reminder_type = 'todo')
     <> (SELECT n FROM protected_todo_reminders) THEN
    RAISE EXCEPTION '待办提醒日志数量变化，停止清理';
  END IF;
  IF (SELECT count(*) FROM anonymized_data WHERE data_type = 'user_profile')
     <> (SELECT n FROM protected_profiles) THEN
    RAISE EXCEPTION '匿名账户记录数量变化，停止清理';
  END IF;
END $check$;

COMMIT;
SQL

# Both paths are fixed Shuran feature directories within the uploads volume.
docker compose run --rm --no-deps --entrypoint python app -c '
from pathlib import Path
import shutil

root = Path("/app/uploads").resolve()
targets = [root / "ebooks", root / "self_talks"]
for target in targets:
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise SystemExit(f"文件类型异常，停止清理：{target}")
for target in targets:
    if target.exists():
        shutil.rmtree(target)
        print(f"已清理：{target}")
'

docker compose start app
trap - EXIT
healthy=0
for attempt in {1..30}; do
  if curl -fsS http://127.0.0.1:8000/health; then
    healthy=1
    break
  fi
  sleep 2
done
if [[ "$healthy" != 1 ]]; then
  echo "数据库与文件清理已执行，但应用健康检查失败；请检查 docker compose logs app。" >&2
  exit 5
fi
echo "清理完成；恢复备份保留在 $backup_dir。"
