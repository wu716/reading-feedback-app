-- 新加坡补迁：按邮箱对齐写入香港。已存在的行跳过。不覆盖香港用户。
-- 不处理 time_log_nodes / anonymized_data / audit_logs。
-- subscriptions：该邮箱在香港已有订阅则跳过，不覆盖。
-- invite_codes：香港已有相同 code 则跳过，不覆盖。
-- 正式表不存在则跳过（新加坡旧库没有 future_actions 时不是数据丢失）。
-- 失败立刻停。禁止 DROP SCHEMA。禁止 docker compose down -v。

BEGIN;

DO $$
DECLARE
  t text;
  seq text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'users','actions','practice_logs','daily_todos','daily_tasks','daily_schedules',
    'future_actions','reading_entries','self_talks','self_talk_playback_logs',
    'ai_advice_sessions','ai_advice_messages','self_talk_reminder_settings',
    'self_talk_reminder_logs','ai_call_logs','subscriptions','invite_codes'
  ]
  LOOP
    IF to_regclass('public.' || t) IS NULL THEN
      RAISE NOTICE '表 % 不存在，跳过序列检查', t;
      CONTINUE;
    END IF;
    seq := pg_get_serial_sequence('public.' || t, 'id');
    IF seq IS NULL THEN
      RAISE EXCEPTION '表 % 没有 id 序列，停', t;
    END IF;
  END LOOP;
END $$;

TRUNCATE sg_id_map;

-- 香港没有的邮箱：新建用户。已有邮箱：不改密码、不改套餐、不改任何字段。
INSERT INTO users (
  email, name, real_name, phone, phone_verified, password_hash, is_active,
  created_at, updated_at, deleted_at, plan, plan_expires_at, token_version
)
SELECT
  s.email,
  COALESCE(NULLIF(btrim(s.name), ''), 'user'),
  s.real_name,
  CASE
    WHEN s.phone IS NULL OR btrim(s.phone) = '' THEN NULL
    WHEN EXISTS (SELECT 1 FROM users u2 WHERE u2.phone = s.phone) THEN NULL
    WHEN EXISTS (
      SELECT 1 FROM sg_stg_users s2
      WHERE s2.phone = s.phone
        AND s2.id < s.id
        AND NOT EXISTS (
          SELECT 1 FROM users u3
          WHERE lower(btrim(u3.email)) = lower(btrim(s2.email))
        )
    ) THEN NULL
    ELSE s.phone
  END,
  COALESCE(s.phone_verified, false),
  s.password_hash,
  COALESCE(s.is_active, true),
  s.created_at,
  s.updated_at,
  s.deleted_at,
  COALESCE(s.plan, 'free'),
  s.plan_expires_at,
  COALESCE(s.token_version, 0)
FROM sg_stg_users s
WHERE s.email IS NOT NULL
  AND btrim(s.email) <> ''
  AND s.password_hash IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM users u
    WHERE lower(btrim(u.email)) = lower(btrim(s.email))
  )
ON CONFLICT (email) DO NOTHING;

-- actions：已有则只记 id 对照；没有则插入
INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT DISTINCT ON (s.id) 'actions', s.id, a.id
FROM sg_stg_actions s
JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.owner_email))
JOIN actions a
  ON a.user_id = u.id
 AND a.created_at IS NOT DISTINCT FROM s.created_at
 AND a.book_title IS NOT DISTINCT FROM s.book_title
 AND a.action_text IS NOT DISTINCT FROM s.action_text
 AND a.source_excerpt IS NOT DISTINCT FROM s.source_excerpt
ORDER BY s.id, a.id
ON CONFLICT (table_name, sg_id) DO NOTHING;

CREATE TEMP TABLE _ins_actions AS
SELECT s.*, u.id AS hk_user_id,
       nextval(pg_get_serial_sequence('public.actions', 'id')) AS new_id
FROM sg_stg_actions s
JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.owner_email))
WHERE NOT EXISTS (
  SELECT 1 FROM sg_id_map m WHERE m.table_name = 'actions' AND m.sg_id = s.id
);

INSERT INTO actions (
  id, user_id, book_title, source_excerpt, action_text, tags, frequency, status,
  action_type, duration_type, target_duration_days, target_frequency,
  custom_frequency_days, start_date, end_date, created_at, updated_at, deleted_at
)
SELECT
  new_id, hk_user_id, book_title, source_excerpt, action_text,
  COALESCE(tags, '[]'), COALESCE(frequency, 'daily'), COALESCE(status, 'todo'),
  COALESCE(action_type, 'trigger'), COALESCE(duration_type, 'short_term'),
  target_duration_days, target_frequency,
  custom_frequency_days, start_date, end_date, created_at, updated_at, deleted_at
FROM _ins_actions;

INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT 'actions', id, new_id FROM _ins_actions;

-- practice_logs：没有对应行动的行跳过
INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT DISTINCT ON (s.id) 'practice_logs', s.id, p.id
FROM sg_stg_practice_logs s
JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.owner_email))
JOIN sg_id_map am ON am.table_name = 'actions' AND am.sg_id = s.action_id
JOIN practice_logs p
  ON p.user_id = u.id
 AND p.action_id = am.hk_id
 AND p.date IS NOT DISTINCT FROM s.date
 AND p.result IS NOT DISTINCT FROM s.result
 AND p.created_at IS NOT DISTINCT FROM s.created_at
ORDER BY s.id, p.id
ON CONFLICT (table_name, sg_id) DO NOTHING;

CREATE TEMP TABLE _ins_practice_logs AS
SELECT s.*, u.id AS hk_user_id, am.hk_id AS hk_action_id,
       nextval(pg_get_serial_sequence('public.practice_logs', 'id')) AS new_id
FROM sg_stg_practice_logs s
JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.owner_email))
JOIN sg_id_map am ON am.table_name = 'actions' AND am.sg_id = s.action_id
WHERE NOT EXISTS (
  SELECT 1 FROM sg_id_map m WHERE m.table_name = 'practice_logs' AND m.sg_id = s.id
);

INSERT INTO practice_logs (
  id, user_id, action_id, date, result, notes, rating, attempt_number,
  success_score, created_at, updated_at, deleted_at
)
SELECT
  new_id, hk_user_id, hk_action_id, date, result, notes, rating, attempt_number,
  success_score, created_at, updated_at, deleted_at
FROM _ins_practice_logs;

INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT 'practice_logs', id, new_id FROM _ins_practice_logs;

-- daily_todos
INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT DISTINCT ON (s.id) 'daily_todos', s.id, t.id
FROM sg_stg_daily_todos s
JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.owner_email))
JOIN daily_todos t
  ON t.user_id = u.id
 AND t.todo_date IS NOT DISTINCT FROM s.todo_date
 AND t.text IS NOT DISTINCT FROM s.text
 AND t.created_at IS NOT DISTINCT FROM s.created_at
ORDER BY s.id, t.id
ON CONFLICT (table_name, sg_id) DO NOTHING;

CREATE TEMP TABLE _ins_daily_todos AS
SELECT s.*, u.id AS hk_user_id,
       nextval(pg_get_serial_sequence('public.daily_todos', 'id')) AS new_id
FROM sg_stg_daily_todos s
JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.owner_email))
WHERE NOT EXISTS (
  SELECT 1 FROM sg_id_map m WHERE m.table_name = 'daily_todos' AND m.sg_id = s.id
);

INSERT INTO daily_todos (
  id, user_id, text, completed, todo_date, remind_time, reminded_at,
  created_at, updated_at, deleted_at
)
SELECT
  new_id, hk_user_id, text, completed, todo_date, remind_time, reminded_at,
  created_at, updated_at, deleted_at
FROM _ins_daily_todos;

INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT 'daily_todos', id, new_id FROM _ins_daily_todos;

-- daily_tasks：先不写 parent_id，插完再补
INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT DISTINCT ON (s.id) 'daily_tasks', s.id, t.id
FROM sg_stg_daily_tasks s
JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.owner_email))
JOIN daily_tasks t
  ON t.user_id = u.id
 AND t.task_date IS NOT DISTINCT FROM s.task_date
 AND t.text IS NOT DISTINCT FROM s.text
 AND t.sort_order IS NOT DISTINCT FROM s.sort_order
 AND t.created_at IS NOT DISTINCT FROM s.created_at
ORDER BY s.id, t.id
ON CONFLICT (table_name, sg_id) DO NOTHING;

CREATE TEMP TABLE _ins_daily_tasks AS
SELECT s.*, u.id AS hk_user_id,
       am.hk_id AS hk_action_id,
       nextval(pg_get_serial_sequence('public.daily_tasks', 'id')) AS new_id
FROM sg_stg_daily_tasks s
JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.owner_email))
LEFT JOIN sg_id_map am ON am.table_name = 'actions' AND am.sg_id = s.action_id
WHERE NOT EXISTS (
  SELECT 1 FROM sg_id_map m WHERE m.table_name = 'daily_tasks' AND m.sg_id = s.id
);

INSERT INTO daily_tasks (
  id, user_id, parent_id, task_date, text, completed, note, sort_order,
  familiarity, estimated_minutes, parallel_group, action_id,
  created_at, updated_at, deleted_at
)
SELECT
  new_id, hk_user_id, NULL, task_date, text, completed, note, sort_order,
  familiarity, estimated_minutes, parallel_group, hk_action_id,
  created_at, updated_at, deleted_at
FROM _ins_daily_tasks;

INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT 'daily_tasks', id, new_id FROM _ins_daily_tasks;

UPDATE daily_tasks t
SET parent_id = pm.hk_id
FROM sg_id_map cm
JOIN sg_stg_daily_tasks s ON s.id = cm.sg_id
JOIN sg_id_map pm ON pm.table_name = 'daily_tasks' AND pm.sg_id = s.parent_id
WHERE cm.table_name = 'daily_tasks'
  AND cm.hk_id = t.id
  AND t.parent_id IS NULL
  AND s.parent_id IS NOT NULL;

-- daily_schedules：同一用户同一天已有则跳过
INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT DISTINCT ON (s.id) 'daily_schedules', s.id, d.id
FROM sg_stg_daily_schedules s
JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.owner_email))
JOIN daily_schedules d
  ON d.user_id = u.id
 AND d.schedule_date IS NOT DISTINCT FROM s.schedule_date
ORDER BY s.id, d.id
ON CONFLICT (table_name, sg_id) DO NOTHING;

CREATE TEMP TABLE _ins_daily_schedules AS
SELECT s.*, u.id AS hk_user_id,
       nextval(pg_get_serial_sequence('public.daily_schedules', 'id')) AS new_id
FROM sg_stg_daily_schedules s
JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.owner_email))
WHERE NOT EXISTS (
  SELECT 1 FROM sg_id_map m WHERE m.table_name = 'daily_schedules' AND m.sg_id = s.id
)
AND NOT EXISTS (
  SELECT 1 FROM daily_schedules d
  WHERE d.user_id = u.id AND d.schedule_date IS NOT DISTINCT FROM s.schedule_date
);

INSERT INTO daily_schedules (
  id, user_id, schedule_date, designed_at, created_at, updated_at
)
SELECT new_id, hk_user_id, schedule_date, designed_at, created_at, updated_at
FROM _ins_daily_schedules;

INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT 'daily_schedules', id, new_id FROM _ins_daily_schedules;

-- future_actions：新加坡旧库没有这张表时暂存为空或未建，跳过；不是数据丢失
DO $$
BEGIN
  IF to_regclass('public.future_actions') IS NULL THEN
    RAISE NOTICE 'future_actions 不存在，跳过合并';
    RETURN;
  END IF;
  IF to_regclass('public.sg_stg_future_actions') IS NULL THEN
    RAISE NOTICE 'sg_stg_future_actions 不存在，跳过合并';
    RETURN;
  END IF;

  INSERT INTO sg_id_map (table_name, sg_id, hk_id)
  SELECT DISTINCT ON (s.id) 'future_actions', s.id, f.id
  FROM sg_stg_future_actions s
  JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.owner_email))
  JOIN future_actions f
    ON f.user_id = u.id
   AND f.text IS NOT DISTINCT FROM s.text
   AND f.created_at IS NOT DISTINCT FROM s.created_at
  ORDER BY s.id, f.id
  ON CONFLICT (table_name, sg_id) DO NOTHING;

  CREATE TEMP TABLE _ins_future_actions AS
  SELECT s.*, u.id AS hk_user_id,
         nextval(pg_get_serial_sequence('public.future_actions', 'id')) AS new_id
  FROM sg_stg_future_actions s
  JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.owner_email))
  WHERE NOT EXISTS (
    SELECT 1 FROM sg_id_map m WHERE m.table_name = 'future_actions' AND m.sg_id = s.id
  );

  INSERT INTO future_actions (id, user_id, text, created_at, updated_at, deleted_at)
  SELECT new_id, hk_user_id, text, created_at, updated_at, deleted_at
  FROM _ins_future_actions;

  INSERT INTO sg_id_map (table_name, sg_id, hk_id)
  SELECT 'future_actions', id, new_id FROM _ins_future_actions;
END $$;

-- reading_entries
INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT DISTINCT ON (s.id) 'reading_entries', s.id, r.id
FROM sg_stg_reading_entries s
JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.owner_email))
JOIN reading_entries r
  ON r.user_id = u.id
 AND r.entry_date IS NOT DISTINCT FROM s.entry_date
 AND r.content IS NOT DISTINCT FROM s.content
 AND r.created_at IS NOT DISTINCT FROM s.created_at
ORDER BY s.id, r.id
ON CONFLICT (table_name, sg_id) DO NOTHING;

CREATE TEMP TABLE _ins_reading_entries AS
SELECT s.*, u.id AS hk_user_id,
       nextval(pg_get_serial_sequence('public.reading_entries', 'id')) AS new_id
FROM sg_stg_reading_entries s
JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.owner_email))
WHERE NOT EXISTS (
  SELECT 1 FROM sg_id_map m WHERE m.table_name = 'reading_entries' AND m.sg_id = s.id
);

INSERT INTO reading_entries (
  id, user_id, book_title, content, reflection, duration_minutes, entry_date,
  created_at, updated_at, deleted_at
)
SELECT
  new_id, hk_user_id, book_title, content, reflection, duration_minutes, entry_date,
  created_at, updated_at, deleted_at
FROM _ins_reading_entries;

INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT 'reading_entries', id, new_id FROM _ins_reading_entries;

-- self_talks：对不上的 action_id 写成空
INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT DISTINCT ON (s.id) 'self_talks', s.id, t.id
FROM sg_stg_self_talks s
JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.owner_email))
JOIN self_talks t
  ON t.user_id = u.id
 AND t.audio_path IS NOT DISTINCT FROM s.audio_path
 AND t.created_at IS NOT DISTINCT FROM s.created_at
ORDER BY s.id, t.id
ON CONFLICT (table_name, sg_id) DO NOTHING;

CREATE TEMP TABLE _ins_self_talks AS
SELECT s.*, u.id AS hk_user_id, am.hk_id AS hk_action_id,
       nextval(pg_get_serial_sequence('public.self_talks', 'id')) AS new_id
FROM sg_stg_self_talks s
JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.owner_email))
LEFT JOIN sg_id_map am ON am.table_name = 'actions' AND am.sg_id = s.action_id
WHERE NOT EXISTS (
  SELECT 1 FROM sg_id_map m WHERE m.table_name = 'self_talks' AND m.sg_id = s.id
);

INSERT INTO self_talks (
  id, user_id, action_id, audio_path, transcript, created_at, updated_at, deleted_at
)
SELECT
  new_id, hk_user_id, hk_action_id, audio_path, transcript, created_at, updated_at, deleted_at
FROM _ins_self_talks;

INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT 'self_talks', id, new_id FROM _ins_self_talks;

-- self_talk_playback_logs：没有对应录音的行跳过
INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT DISTINCT ON (s.id) 'self_talk_playback_logs', s.id, p.id
FROM sg_stg_self_talk_playback_logs s
JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.owner_email))
JOIN sg_id_map tm ON tm.table_name = 'self_talks' AND tm.sg_id = s.self_talk_id
JOIN self_talk_playback_logs p
  ON p.user_id = u.id
 AND p.self_talk_id = tm.hk_id
 AND p.play_date IS NOT DISTINCT FROM s.play_date
 AND p.created_at IS NOT DISTINCT FROM s.created_at
ORDER BY s.id, p.id
ON CONFLICT (table_name, sg_id) DO NOTHING;

CREATE TEMP TABLE _ins_playback AS
SELECT s.*, u.id AS hk_user_id, tm.hk_id AS hk_self_talk_id,
       nextval(pg_get_serial_sequence('public.self_talk_playback_logs', 'id')) AS new_id
FROM sg_stg_self_talk_playback_logs s
JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.owner_email))
JOIN sg_id_map tm ON tm.table_name = 'self_talks' AND tm.sg_id = s.self_talk_id
WHERE NOT EXISTS (
  SELECT 1 FROM sg_id_map m WHERE m.table_name = 'self_talk_playback_logs' AND m.sg_id = s.id
);

INSERT INTO self_talk_playback_logs (
  id, user_id, self_talk_id, play_date, duration_seconds, loops_completed,
  loop_mode, loop_target, created_at
)
SELECT
  new_id, hk_user_id, hk_self_talk_id, play_date, duration_seconds, loops_completed,
  loop_mode, loop_target, created_at
FROM _ins_playback;

INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT 'self_talk_playback_logs', id, new_id FROM _ins_playback;

-- ai_advice_sessions：session_id 已存在则跳过；没有对应行动的行跳过
INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT DISTINCT ON (s.id) 'ai_advice_sessions', s.id, x.id
FROM sg_stg_ai_advice_sessions s
JOIN ai_advice_sessions x ON x.session_id = s.session_id
ORDER BY s.id, x.id
ON CONFLICT (table_name, sg_id) DO NOTHING;

CREATE TEMP TABLE _ins_ai_sessions AS
SELECT s.*, u.id AS hk_user_id, am.hk_id AS hk_action_id,
       nextval(pg_get_serial_sequence('public.ai_advice_sessions', 'id')) AS new_id
FROM sg_stg_ai_advice_sessions s
JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.owner_email))
JOIN sg_id_map am ON am.table_name = 'actions' AND am.sg_id = s.action_id
WHERE NOT EXISTS (
  SELECT 1 FROM sg_id_map m WHERE m.table_name = 'ai_advice_sessions' AND m.sg_id = s.id
)
AND NOT EXISTS (
  SELECT 1 FROM ai_advice_sessions x WHERE x.session_id = s.session_id
);

INSERT INTO ai_advice_sessions (
  id, session_id, user_id, action_id, model_type, web_search_enabled, is_active,
  last_message_at, created_at, updated_at, deleted_at
)
SELECT
  new_id, session_id, hk_user_id, hk_action_id, model_type, web_search_enabled, is_active,
  last_message_at, created_at, updated_at, deleted_at
FROM _ins_ai_sessions;

INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT 'ai_advice_sessions', id, new_id FROM _ins_ai_sessions;

-- ai_advice_messages
INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT DISTINCT ON (s.id) 'ai_advice_messages', s.id, m.id
FROM sg_stg_ai_advice_messages s
JOIN sg_id_map sm ON sm.table_name = 'ai_advice_sessions' AND sm.sg_id = s.session_id
JOIN ai_advice_messages m
  ON m.session_id = sm.hk_id
 AND m.created_at IS NOT DISTINCT FROM s.created_at
 AND m.role IS NOT DISTINCT FROM s.role
 AND m.content IS NOT DISTINCT FROM s.content
ORDER BY s.id, m.id
ON CONFLICT (table_name, sg_id) DO NOTHING;

CREATE TEMP TABLE _ins_ai_messages AS
SELECT s.*, sm.hk_id AS hk_session_id,
       nextval(pg_get_serial_sequence('public.ai_advice_messages', 'id')) AS new_id
FROM sg_stg_ai_advice_messages s
JOIN sg_id_map sm ON sm.table_name = 'ai_advice_sessions' AND sm.sg_id = s.session_id
WHERE NOT EXISTS (
  SELECT 1 FROM sg_id_map m WHERE m.table_name = 'ai_advice_messages' AND m.sg_id = s.id
);

INSERT INTO ai_advice_messages (
  id, session_id, role, content, thinking_process, web_search_results,
  token_count, model_used, created_at, updated_at, deleted_at
)
SELECT
  new_id, hk_session_id, role, content, thinking_process, web_search_results,
  token_count, model_used, created_at, updated_at, deleted_at
FROM _ins_ai_messages;

INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT 'ai_advice_messages', id, new_id FROM _ins_ai_messages;

-- 提醒设置：每个用户只保留香港已有的；没有才插入
INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT DISTINCT ON (s.id) 'self_talk_reminder_settings', s.id, r.id
FROM sg_stg_self_talk_reminder_settings s
JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.owner_email))
JOIN self_talk_reminder_settings r ON r.user_id = u.id
ORDER BY s.id, r.id
ON CONFLICT (table_name, sg_id) DO NOTHING;

CREATE TEMP TABLE _ins_reminder_settings AS
SELECT s.*, u.id AS hk_user_id,
       nextval(pg_get_serial_sequence('public.self_talk_reminder_settings', 'id')) AS new_id
FROM sg_stg_self_talk_reminder_settings s
JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.owner_email))
WHERE NOT EXISTS (
  SELECT 1 FROM sg_id_map m
  WHERE m.table_name = 'self_talk_reminder_settings' AND m.sg_id = s.id
)
AND NOT EXISTS (
  SELECT 1 FROM self_talk_reminder_settings r WHERE r.user_id = u.id
);

INSERT INTO self_talk_reminder_settings (
  id, user_id, is_enabled, daily_reminder_enabled, daily_reminder_time, reminder_days,
  after_action_reminder, after_new_action_reminder, inactive_days_threshold,
  browser_notification, email_notification, reading_reminder_enabled,
  reading_reminder_time, created_at, updated_at
)
SELECT
  new_id, hk_user_id,
  COALESCE(is_enabled, true),
  COALESCE(daily_reminder_enabled, false), daily_reminder_time, reminder_days,
  COALESCE(after_action_reminder, true), COALESCE(after_new_action_reminder, true),
  COALESCE(inactive_days_threshold, 3),
  COALESCE(browser_notification, true), COALESCE(email_notification, true),
  COALESCE(reading_reminder_enabled, false),
  reading_reminder_time, created_at, updated_at
FROM _ins_reminder_settings;

INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT 'self_talk_reminder_settings', id, new_id FROM _ins_reminder_settings;

-- self_talk_reminder_logs
INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT DISTINCT ON (s.id) 'self_talk_reminder_logs', s.id, r.id
FROM sg_stg_self_talk_reminder_logs s
JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.owner_email))
JOIN self_talk_reminder_logs r
  ON r.user_id = u.id
 AND r.reminder_type IS NOT DISTINCT FROM s.reminder_type
 AND r.triggered_at IS NOT DISTINCT FROM s.triggered_at
ORDER BY s.id, r.id
ON CONFLICT (table_name, sg_id) DO NOTHING;

CREATE TEMP TABLE _ins_reminder_logs AS
SELECT s.*, u.id AS hk_user_id,
       nextval(pg_get_serial_sequence('public.self_talk_reminder_logs', 'id')) AS new_id
FROM sg_stg_self_talk_reminder_logs s
JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.owner_email))
WHERE NOT EXISTS (
  SELECT 1 FROM sg_id_map m WHERE m.table_name = 'self_talk_reminder_logs' AND m.sg_id = s.id
);

INSERT INTO self_talk_reminder_logs (
  id, user_id, reminder_type, detail, triggered_at, dismissed_at,
  action_taken, notification_method
)
SELECT
  new_id, hk_user_id, reminder_type, detail, triggered_at, dismissed_at,
  action_taken, notification_method
FROM _ins_reminder_logs;

INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT 'self_talk_reminder_logs', id, new_id FROM _ins_reminder_logs;

-- ai_call_logs
INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT DISTINCT ON (s.id) 'ai_call_logs', s.id, c.id
FROM sg_stg_ai_call_logs s
JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.owner_email))
JOIN ai_call_logs c
  ON c.user_id = u.id
 AND c.kind IS NOT DISTINCT FROM s.kind
 AND c.call_date IS NOT DISTINCT FROM s.call_date
 AND c.created_at IS NOT DISTINCT FROM s.created_at
ORDER BY s.id, c.id
ON CONFLICT (table_name, sg_id) DO NOTHING;

CREATE TEMP TABLE _ins_ai_call_logs AS
SELECT s.*, u.id AS hk_user_id,
       nextval(pg_get_serial_sequence('public.ai_call_logs', 'id')) AS new_id
FROM sg_stg_ai_call_logs s
JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.owner_email))
WHERE NOT EXISTS (
  SELECT 1 FROM sg_id_map m WHERE m.table_name = 'ai_call_logs' AND m.sg_id = s.id
);

INSERT INTO ai_call_logs (id, user_id, kind, call_date, created_at)
SELECT new_id, hk_user_id, kind, call_date, created_at
FROM _ins_ai_call_logs;

INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT 'ai_call_logs', id, new_id FROM _ins_ai_call_logs;

-- subscriptions：香港该邮箱已有订阅则跳过，不覆盖、不改 users.plan
INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT DISTINCT ON (s.id) 'subscriptions', s.id, x.id
FROM sg_stg_subscriptions s
JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.owner_email))
JOIN subscriptions x ON x.user_id = u.id
ORDER BY s.id, x.id
ON CONFLICT (table_name, sg_id) DO NOTHING;

CREATE TEMP TABLE _ins_subscriptions AS
SELECT DISTINCT ON (u.id) s.*, u.id AS hk_user_id,
       nextval(pg_get_serial_sequence('public.subscriptions', 'id')) AS new_id
FROM sg_stg_subscriptions s
JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.owner_email))
WHERE s.plan IS NOT NULL
  AND s.start_date IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sg_id_map m WHERE m.table_name = 'subscriptions' AND m.sg_id = s.id
  )
  AND NOT EXISTS (
    SELECT 1 FROM subscriptions x WHERE x.user_id = u.id
  )
ORDER BY u.id, s.id;

INSERT INTO subscriptions (
  id, user_id, plan, start_date, end_date, is_active, created_at, updated_at
)
SELECT
  new_id, hk_user_id, plan, start_date, end_date,
  COALESCE(is_active, true), created_at, updated_at
FROM _ins_subscriptions;

INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT 'subscriptions', id, new_id FROM _ins_subscriptions;

-- invite_codes：香港已有相同 code 则跳过，不覆盖
INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT DISTINCT ON (s.id) 'invite_codes', s.id, i.id
FROM sg_stg_invite_codes s
JOIN invite_codes i ON i.code = s.code
WHERE s.code IS NOT NULL AND btrim(s.code) <> ''
ORDER BY s.id, i.id
ON CONFLICT (table_name, sg_id) DO NOTHING;

CREATE TEMP TABLE _ins_invite_codes AS
SELECT s.*, u.id AS hk_used_by_id,
       nextval(pg_get_serial_sequence('public.invite_codes', 'id')) AS new_id
FROM sg_stg_invite_codes s
LEFT JOIN users u
  ON s.used_by_email IS NOT NULL
 AND btrim(s.used_by_email) <> ''
 AND lower(btrim(u.email)) = lower(btrim(s.used_by_email))
WHERE s.code IS NOT NULL
  AND btrim(s.code) <> ''
  AND NOT EXISTS (
    SELECT 1 FROM sg_id_map m WHERE m.table_name = 'invite_codes' AND m.sg_id = s.id
  )
  AND NOT EXISTS (
    SELECT 1 FROM invite_codes i WHERE i.code = s.code
  );

INSERT INTO invite_codes (
  id, code, plan, note, expires_at, used_at, used_by_user_id, created_at
)
SELECT
  new_id, code, COALESCE(plan, 'free'), note,
  COALESCE(expires_at, now() + interval '365 days'),
  used_at, hk_used_by_id, created_at
FROM _ins_invite_codes;

INSERT INTO sg_id_map (table_name, sg_id, hk_id)
SELECT 'invite_codes', id, new_id FROM _ins_invite_codes;

DO $$
DECLARE
  t text;
  seq text;
  max_id bigint;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'users','actions','practice_logs','daily_todos','daily_tasks','daily_schedules',
    'future_actions','reading_entries','self_talks','self_talk_playback_logs',
    'ai_advice_sessions','ai_advice_messages','self_talk_reminder_settings',
    'self_talk_reminder_logs','ai_call_logs','subscriptions','invite_codes'
  ]
  LOOP
    IF to_regclass('public.' || t) IS NULL THEN
      RAISE NOTICE '表 % 不存在，跳过序列校正', t;
      CONTINUE;
    END IF;
    seq := pg_get_serial_sequence('public.' || t, 'id');
    IF seq IS NULL THEN
      RAISE EXCEPTION '表 % 没有 id 序列，停', t;
    END IF;
    EXECUTE format('SELECT COALESCE(MAX(id), 1) FROM %I', t) INTO max_id;
    PERFORM setval(seq, max_id);
  END LOOP;
END $$;

COMMIT;

SELECT 'MERGE_OK' AS status;
SELECT table_name, count(*) AS mapped_rows FROM sg_id_map GROUP BY table_name ORDER BY table_name;
SELECT 'practice_logs_skipped_no_action' AS reason, count(*) AS n
FROM sg_stg_practice_logs s
WHERE NOT EXISTS (SELECT 1 FROM sg_id_map m WHERE m.table_name = 'actions' AND m.sg_id = s.action_id);
SELECT 'self_talk_playback_skipped_no_talk' AS reason, count(*) AS n
FROM sg_stg_self_talk_playback_logs s
WHERE NOT EXISTS (SELECT 1 FROM sg_id_map m WHERE m.table_name = 'self_talks' AND m.sg_id = s.self_talk_id);
SELECT 'ai_sessions_skipped_no_action' AS reason, count(*) AS n
FROM sg_stg_ai_advice_sessions s
WHERE NOT EXISTS (SELECT 1 FROM sg_id_map m WHERE m.table_name = 'actions' AND m.sg_id = s.action_id)
  AND NOT EXISTS (SELECT 1 FROM ai_advice_sessions x WHERE x.session_id = s.session_id);
SELECT s.email AS sg_email, s.plan AS sg_plan, u.plan AS hk_plan
FROM sg_stg_users s
JOIN users u ON lower(btrim(u.email)) = lower(btrim(s.email))
WHERE s.plan IS DISTINCT FROM u.plan
ORDER BY s.email;
