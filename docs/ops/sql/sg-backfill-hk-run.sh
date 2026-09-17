#!/bin/bash
# 香港补迁合并：按邮箱对齐写入用户内容。不碰 time_log_nodes。
# 禁止 DROP SCHEMA。禁止 docker compose down -v。禁止 compose --build。
# 缺 csv / 缺表跳过。不覆盖香港已有同邮箱用户的账号密码。
set -e
set -o pipefail

SQL_DIR="${SQL_DIR:-/tmp/sg-sql}"
if [ -f /opt/shuran-app/docs/ops/sql/sg-backfill-02-merge.sql ]; then
  SQL_DIR=/opt/shuran-app/docs/ops/sql
fi
test -f "$SQL_DIR/sg-backfill-01-staging.sql"
test -f "$SQL_DIR/sg-backfill-02-merge.sql"
test -f "$SQL_DIR/sg-backfill-03-verify.sql"

echo "=== ls /tmp/sg-backfill ==="
ls -lh /tmp/sg-backfill
test -d /tmp/sg-backfill
test -s /tmp/sg-backfill/users.csv
if [ -f /tmp/sg-backfill/time_log_nodes.csv ]; then
  echo "ERROR 发现 time_log_nodes.csv，拒绝继续（时间日志已迁完，禁止再合并）"
  exit 1
fi

cd /opt/shuran-app/deploy/aliyun

pg () {
  docker compose exec -T db psql -U reading_app -d reading_feedback -v ON_ERROR_STOP=1 "$@"
}

echo "=== 合并前行数 ==="
: > /tmp/hk_counts_before.txt
for t in users actions practice_logs daily_todos daily_tasks daily_schedules future_actions reading_entries self_talks self_talk_playback_logs ai_advice_sessions ai_advice_messages self_talk_reminder_settings self_talk_reminder_logs ai_call_logs subscriptions invite_codes time_log_nodes
do
  exists=$(pg -tAc "SELECT to_regclass('public.${t}') IS NOT NULL" | tr -d '[:space:]')
  if [ "$exists" = "t" ]; then
    pg -c "SELECT '${t}' AS t, count(*) FROM ${t}" | tee -a /tmp/hk_counts_before.txt
  else
    echo "${t} SKIP_NOT_EXISTS" | tee -a /tmp/hk_counts_before.txt
  fi
done
pg -c "SELECT log_date, count(*) AS n FROM time_log_nodes GROUP BY log_date ORDER BY log_date DESC;" | tee -a /tmp/hk_counts_before.txt
TLN_BEFORE=$(pg -tAc "SELECT count(*) FROM time_log_nodes" | tr -d '[:space:]')
echo "time_log_nodes_before=${TLN_BEFORE}" | tee -a /tmp/hk_counts_before.txt

echo "=== 建暂存表 ==="
docker compose exec -T db psql -U reading_app -d reading_feedback -v ON_ERROR_STOP=1 \
  < "$SQL_DIR/sg-backfill-01-staging.sql"

header_cols () {
  local file="$1"
  head -n 1 "$file" | tr -d '\r' | awk -F',' '{
    out = ""
    for (i = 1; i <= NF; i++) {
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", $i)
      gsub(/^"/, "", $i)
      gsub(/"$/, "", $i)
      if ($i == "") continue
      if (out != "") out = out ", "
      out = out "\"" $i "\""
    }
    print out
  }'
}

load_csv () {
  local table="$1"
  local file="$2"
  local cols
  if [ ! -f "/tmp/sg-backfill/${file}" ]; then
    echo "SKIP ${table} (没有 ${file}，新加坡没有这张表，不是数据丢失)"
    return 0
  fi
  if [ ! -s "/tmp/sg-backfill/${file}" ]; then
    echo "ERROR ${file} 是空文件"
    exit 1
  fi
  cols=$(header_cols "/tmp/sg-backfill/${file}")
  if [ -z "$cols" ]; then
    echo "ERROR ${file} 表头是空的"
    exit 1
  fi
  echo "LOAD ${table}"
  echo "COLS ${table}: ${cols}"
  docker compose exec -T db psql -U reading_app -d reading_feedback -v ON_ERROR_STOP=1 \
    -c "COPY ${table} (${cols}) FROM STDIN WITH (FORMAT csv, HEADER true)" \
    < "/tmp/sg-backfill/${file}"
}

load_csv sg_stg_users users.csv
load_csv sg_stg_actions actions.csv
load_csv sg_stg_practice_logs practice_logs.csv
load_csv sg_stg_daily_todos daily_todos.csv
load_csv sg_stg_daily_tasks daily_tasks.csv
load_csv sg_stg_daily_schedules daily_schedules.csv
load_csv sg_stg_future_actions future_actions.csv
load_csv sg_stg_reading_entries reading_entries.csv
load_csv sg_stg_self_talks self_talks.csv
load_csv sg_stg_self_talk_playback_logs self_talk_playback_logs.csv
load_csv sg_stg_ai_advice_sessions ai_advice_sessions.csv
load_csv sg_stg_ai_advice_messages ai_advice_messages.csv
load_csv sg_stg_self_talk_reminder_settings self_talk_reminder_settings.csv
load_csv sg_stg_self_talk_reminder_logs self_talk_reminder_logs.csv
load_csv sg_stg_ai_call_logs ai_call_logs.csv
load_csv sg_stg_subscriptions subscriptions.csv
load_csv sg_stg_invite_codes invite_codes.csv

echo "=== 按邮箱合并 ==="
docker compose exec -T db psql -U reading_app -d reading_feedback -v ON_ERROR_STOP=1 \
  < "$SQL_DIR/sg-backfill-02-merge.sql"

echo "=== 合并后核对 ==="
docker compose exec -T db psql -U reading_app -d reading_feedback -v ON_ERROR_STOP=1 \
  < "$SQL_DIR/sg-backfill-03-verify.sql" | tee /tmp/hk_counts_after.txt

TLN_AFTER=$(pg -tAc "SELECT count(*) FROM time_log_nodes" | tr -d '[:space:]')
echo "time_log_nodes_after=${TLN_AFTER}"
if [ "${TLN_BEFORE}" != "${TLN_AFTER}" ]; then
  echo "ERROR time_log_nodes 数量被改了: ${TLN_BEFORE} -> ${TLN_AFTER}"
  exit 1
fi

if [ -f /tmp/sg-backfill/uploads-self-talks.tgz ]; then
  echo "=== 解压 self_talks 音频（不覆盖香港已有文件）==="
  UPLOAD_VOL=$(docker volume ls -q | grep -E 'uploads' | head -n 1)
  if [ -z "$UPLOAD_VOL" ]; then
    echo "ERROR 找不到 uploads volume"
    exit 1
  fi
  docker run --rm -v "${UPLOAD_VOL}:/data" -v /tmp/sg-backfill:/backup alpine sh -c '
    mkdir -p /data/self_talks /tmp/sgup
    tar xzf /backup/uploads-self-talks.tgz -C /tmp/sgup
    if [ -d /tmp/sgup/self_talks ]; then src=/tmp/sgup/self_talks; else src=/tmp/sgup; fi
    cp -n "$src"/* /data/self_talks/ 2>/dev/null || true
    echo UPLOADS_MERGED
    ls /data/self_talks | wc -l
  '
else
  echo "SKIP uploads-self-talks.tgz（没有这个文件）"
fi

echo HK_MERGE_OK
