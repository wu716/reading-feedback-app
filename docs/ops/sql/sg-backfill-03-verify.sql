-- 补迁后核对。只读。不要 DROP SCHEMA。

SELECT 'time_log_nodes_by_day' AS check;
SELECT log_date, count(*) AS n
FROM time_log_nodes
GROUP BY log_date
ORDER BY log_date DESC;

SELECT 'table_counts' AS check;
SELECT 'users' AS t, count(*) FROM users
UNION ALL SELECT 'actions', count(*) FROM actions
UNION ALL SELECT 'practice_logs', count(*) FROM practice_logs
UNION ALL SELECT 'daily_todos', count(*) FROM daily_todos
UNION ALL SELECT 'daily_tasks', count(*) FROM daily_tasks
UNION ALL SELECT 'daily_schedules', count(*) FROM daily_schedules
UNION ALL SELECT 'future_actions', count(*) FROM future_actions
UNION ALL SELECT 'reading_entries', count(*) FROM reading_entries
UNION ALL SELECT 'self_talks', count(*) FROM self_talks
UNION ALL SELECT 'self_talk_playback_logs', count(*) FROM self_talk_playback_logs
UNION ALL SELECT 'ai_advice_sessions', count(*) FROM ai_advice_sessions
UNION ALL SELECT 'ai_advice_messages', count(*) FROM ai_advice_messages
UNION ALL SELECT 'self_talk_reminder_settings', count(*) FROM self_talk_reminder_settings
UNION ALL SELECT 'self_talk_reminder_logs', count(*) FROM self_talk_reminder_logs
UNION ALL SELECT 'ai_call_logs', count(*) FROM ai_call_logs
UNION ALL SELECT 'time_log_nodes', count(*) FROM time_log_nodes
ORDER BY 1;

SELECT 'staging_vs_mapped' AS check;
SELECT 'actions' AS t, (SELECT count(*) FROM sg_stg_actions) AS sg_csv,
       (SELECT count(*) FROM sg_id_map WHERE table_name = 'actions') AS mapped
UNION ALL SELECT 'practice_logs', (SELECT count(*) FROM sg_stg_practice_logs),
       (SELECT count(*) FROM sg_id_map WHERE table_name = 'practice_logs')
UNION ALL SELECT 'daily_todos', (SELECT count(*) FROM sg_stg_daily_todos),
       (SELECT count(*) FROM sg_id_map WHERE table_name = 'daily_todos')
UNION ALL SELECT 'daily_tasks', (SELECT count(*) FROM sg_stg_daily_tasks),
       (SELECT count(*) FROM sg_id_map WHERE table_name = 'daily_tasks')
UNION ALL SELECT 'daily_schedules', (SELECT count(*) FROM sg_stg_daily_schedules),
       (SELECT count(*) FROM sg_id_map WHERE table_name = 'daily_schedules')
UNION ALL SELECT 'future_actions', (SELECT count(*) FROM sg_stg_future_actions),
       (SELECT count(*) FROM sg_id_map WHERE table_name = 'future_actions')
UNION ALL SELECT 'reading_entries', (SELECT count(*) FROM sg_stg_reading_entries),
       (SELECT count(*) FROM sg_id_map WHERE table_name = 'reading_entries')
UNION ALL SELECT 'self_talks', (SELECT count(*) FROM sg_stg_self_talks),
       (SELECT count(*) FROM sg_id_map WHERE table_name = 'self_talks')
UNION ALL SELECT 'self_talk_playback_logs', (SELECT count(*) FROM sg_stg_self_talk_playback_logs),
       (SELECT count(*) FROM sg_id_map WHERE table_name = 'self_talk_playback_logs')
UNION ALL SELECT 'ai_advice_sessions', (SELECT count(*) FROM sg_stg_ai_advice_sessions),
       (SELECT count(*) FROM sg_id_map WHERE table_name = 'ai_advice_sessions')
UNION ALL SELECT 'ai_advice_messages', (SELECT count(*) FROM sg_stg_ai_advice_messages),
       (SELECT count(*) FROM sg_id_map WHERE table_name = 'ai_advice_messages')
UNION ALL SELECT 'self_talk_reminder_settings', (SELECT count(*) FROM sg_stg_self_talk_reminder_settings),
       (SELECT count(*) FROM sg_id_map WHERE table_name = 'self_talk_reminder_settings')
UNION ALL SELECT 'self_talk_reminder_logs', (SELECT count(*) FROM sg_stg_self_talk_reminder_logs),
       (SELECT count(*) FROM sg_id_map WHERE table_name = 'self_talk_reminder_logs')
UNION ALL SELECT 'ai_call_logs', (SELECT count(*) FROM sg_stg_ai_call_logs),
       (SELECT count(*) FROM sg_id_map WHERE table_name = 'ai_call_logs');

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
