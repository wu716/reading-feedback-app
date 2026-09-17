-- 补迁后核对。只读。不要 DROP SCHEMA。

SELECT 'time_log_nodes_by_day' AS check;
SELECT log_date, count(*) AS n
FROM time_log_nodes
GROUP BY log_date
ORDER BY log_date DESC;

SELECT 'table_counts' AS check;
SELECT n.t,
       CASE
         WHEN to_regclass('public.' || n.t) IS NULL THEN -1
         ELSE (
           xpath(
             '//row/c/text()',
             query_to_xml(format('SELECT count(*) AS c FROM %I', n.t), false, true, '')
           )
         )[1]::text::bigint
       END AS n
FROM (
  VALUES
    ('users'),('actions'),('practice_logs'),('daily_todos'),('daily_tasks'),
    ('daily_schedules'),('future_actions'),('reading_entries'),('self_talks'),
    ('self_talk_playback_logs'),('ai_advice_sessions'),('ai_advice_messages'),
    ('self_talk_reminder_settings'),('self_talk_reminder_logs'),('ai_call_logs'),
    ('time_log_nodes')
) AS n(t)
ORDER BY 1;

SELECT 'staging_vs_mapped' AS check;
SELECT n.t,
       CASE
         WHEN to_regclass('public.' || n.stg) IS NULL THEN -1
         ELSE (
           xpath(
             '//row/c/text()',
             query_to_xml(format('SELECT count(*) AS c FROM %I', n.stg), false, true, '')
           )
         )[1]::text::bigint
       END AS sg_csv,
       (SELECT count(*) FROM sg_id_map m WHERE m.table_name = n.t) AS mapped
FROM (
  VALUES
    ('actions', 'sg_stg_actions'),
    ('practice_logs', 'sg_stg_practice_logs'),
    ('daily_todos', 'sg_stg_daily_todos'),
    ('daily_tasks', 'sg_stg_daily_tasks'),
    ('daily_schedules', 'sg_stg_daily_schedules'),
    ('future_actions', 'sg_stg_future_actions'),
    ('reading_entries', 'sg_stg_reading_entries'),
    ('self_talks', 'sg_stg_self_talks'),
    ('self_talk_playback_logs', 'sg_stg_self_talk_playback_logs'),
    ('ai_advice_sessions', 'sg_stg_ai_advice_sessions'),
    ('ai_advice_messages', 'sg_stg_ai_advice_messages'),
    ('self_talk_reminder_settings', 'sg_stg_self_talk_reminder_settings'),
    ('self_talk_reminder_logs', 'sg_stg_self_talk_reminder_logs'),
    ('ai_call_logs', 'sg_stg_ai_call_logs')
) AS n(t, stg);

SELECT 'sg_emails_missing_on_hk' AS check;
SELECT s.email
FROM sg_stg_users s
WHERE s.email IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM users u WHERE lower(btrim(u.email)) = lower(btrim(s.email))
  )
ORDER BY 1;

SELECT 'plan_mismatch_not_auto_updated' AS check;
SELECT s.email, s.plan AS sg_plan, u.plan AS hk_plan
FROM sg_stg_users s
JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.email))
WHERE s.plan IS DISTINCT FROM u.plan
ORDER BY s.email;
