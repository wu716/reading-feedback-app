-- 新加坡补迁：香港机创建暂存表。不含外键。
-- 失败立刻停。禁止 DROP SCHEMA。禁止 docker compose down -v。

DROP TABLE IF EXISTS
  sg_stg_ai_advice_messages,
  sg_stg_ai_advice_sessions,
  sg_stg_self_talk_playback_logs,
  sg_stg_self_talks,
  sg_stg_practice_logs,
  sg_stg_daily_tasks,
  sg_stg_daily_todos,
  sg_stg_daily_schedules,
  sg_stg_future_actions,
  sg_stg_reading_entries,
  sg_stg_self_talk_reminder_settings,
  sg_stg_self_talk_reminder_logs,
  sg_stg_ai_call_logs,
  sg_stg_actions,
  sg_stg_users;

CREATE TABLE sg_stg_users (
  id INTEGER,
  email TEXT,
  name TEXT,
  real_name TEXT,
  phone TEXT,
  phone_verified BOOLEAN,
  password_hash TEXT,
  is_active BOOLEAN,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  deleted_at TIMESTAMPTZ,
  plan TEXT,
  plan_expires_at DATE,
  token_version INTEGER
);

CREATE TABLE sg_stg_actions (
  id INTEGER,
  user_id INTEGER,
  book_title TEXT,
  source_excerpt TEXT,
  action_text TEXT,
  tags TEXT,
  frequency TEXT,
  status TEXT,
  action_type TEXT,
  duration_type TEXT,
  target_duration_days INTEGER,
  target_frequency TEXT,
  custom_frequency_days INTEGER,
  start_date DATE,
  end_date DATE,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  deleted_at TIMESTAMPTZ,
  owner_email TEXT
);

CREATE TABLE sg_stg_practice_logs (
  id INTEGER,
  user_id INTEGER,
  action_id INTEGER,
  date DATE,
  result TEXT,
  notes TEXT,
  rating INTEGER,
  attempt_number INTEGER,
  success_score INTEGER,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  deleted_at TIMESTAMPTZ,
  owner_email TEXT
);

CREATE TABLE sg_stg_daily_todos (
  id INTEGER,
  user_id INTEGER,
  text TEXT,
  completed BOOLEAN,
  todo_date DATE,
  remind_time TEXT,
  reminded_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  deleted_at TIMESTAMPTZ,
  owner_email TEXT
);

CREATE TABLE sg_stg_daily_tasks (
  id INTEGER,
  user_id INTEGER,
  parent_id INTEGER,
  task_date DATE,
  text TEXT,
  completed BOOLEAN,
  note TEXT,
  sort_order INTEGER,
  familiarity TEXT,
  estimated_minutes INTEGER,
  parallel_group INTEGER,
  action_id INTEGER,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  deleted_at TIMESTAMPTZ,
  owner_email TEXT
);

CREATE TABLE sg_stg_daily_schedules (
  id INTEGER,
  user_id INTEGER,
  schedule_date DATE,
  designed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  owner_email TEXT
);

CREATE TABLE sg_stg_future_actions (
  id INTEGER,
  user_id INTEGER,
  text TEXT,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  deleted_at TIMESTAMPTZ,
  owner_email TEXT
);

CREATE TABLE sg_stg_reading_entries (
  id INTEGER,
  user_id INTEGER,
  book_title TEXT,
  content TEXT,
  reflection TEXT,
  duration_minutes INTEGER,
  entry_date DATE,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  deleted_at TIMESTAMPTZ,
  owner_email TEXT
);

CREATE TABLE sg_stg_self_talks (
  id INTEGER,
  user_id INTEGER,
  action_id INTEGER,
  audio_path TEXT,
  transcript TEXT,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  deleted_at TIMESTAMPTZ,
  owner_email TEXT
);

CREATE TABLE sg_stg_self_talk_playback_logs (
  id INTEGER,
  user_id INTEGER,
  self_talk_id INTEGER,
  play_date DATE,
  duration_seconds INTEGER,
  loops_completed INTEGER,
  loop_mode TEXT,
  loop_target INTEGER,
  created_at TIMESTAMPTZ,
  owner_email TEXT
);

CREATE TABLE sg_stg_ai_advice_sessions (
  id INTEGER,
  session_id TEXT,
  user_id INTEGER,
  action_id INTEGER,
  model_type TEXT,
  web_search_enabled BOOLEAN,
  is_active BOOLEAN,
  last_message_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  deleted_at TIMESTAMPTZ,
  owner_email TEXT
);

CREATE TABLE sg_stg_ai_advice_messages (
  id INTEGER,
  session_id INTEGER,
  role TEXT,
  content TEXT,
  thinking_process TEXT,
  web_search_results TEXT,
  token_count INTEGER,
  model_used TEXT,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  deleted_at TIMESTAMPTZ,
  owner_email TEXT
);

CREATE TABLE sg_stg_self_talk_reminder_settings (
  id INTEGER,
  user_id INTEGER,
  is_enabled BOOLEAN,
  daily_reminder_enabled BOOLEAN,
  daily_reminder_time TEXT,
  reminder_days TEXT,
  after_action_reminder BOOLEAN,
  after_new_action_reminder BOOLEAN,
  inactive_days_threshold INTEGER,
  browser_notification BOOLEAN,
  email_notification BOOLEAN,
  reading_reminder_enabled BOOLEAN,
  reading_reminder_time TEXT,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  owner_email TEXT
);

CREATE TABLE sg_stg_self_talk_reminder_logs (
  id INTEGER,
  user_id INTEGER,
  reminder_type TEXT,
  detail TEXT,
  triggered_at TIMESTAMPTZ,
  dismissed_at TIMESTAMPTZ,
  action_taken BOOLEAN,
  notification_method TEXT,
  owner_email TEXT
);

CREATE TABLE sg_stg_ai_call_logs (
  id INTEGER,
  user_id INTEGER,
  kind TEXT,
  call_date DATE,
  created_at TIMESTAMPTZ,
  owner_email TEXT
);

CREATE TABLE IF NOT EXISTS sg_id_map (
  table_name TEXT NOT NULL,
  sg_id INTEGER NOT NULL,
  hk_id INTEGER NOT NULL,
  PRIMARY KEY (table_name, sg_id)
);
