-- AI建议功能数据库迁移SQL脚本
-- 请在SQLite工具中执行这些SQL语句

-- 创建AI建议会话表
CREATE TABLE IF NOT EXISTS ai_advice_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id VARCHAR(50) UNIQUE NOT NULL,
    user_id INTEGER NOT NULL,
    action_id INTEGER NOT NULL,
    model_type VARCHAR(20) DEFAULT 'deepseek-chat',
    web_search_enabled BOOLEAN DEFAULT 0,
    is_active BOOLEAN DEFAULT 1,
    last_message_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    deleted_at DATETIME,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (action_id) REFERENCES actions (id) ON DELETE CASCADE
);

-- 创建AI建议消息表
CREATE TABLE IF NOT EXISTS ai_advice_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    thinking_process TEXT,
    web_search_results TEXT,
    token_count INTEGER,
    model_used VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    deleted_at DATETIME,
    FOREIGN KEY (session_id) REFERENCES ai_advice_sessions (id) ON DELETE CASCADE
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_ai_advice_sessions_user_id ON ai_advice_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_advice_sessions_action_id ON ai_advice_sessions(action_id);
CREATE INDEX IF NOT EXISTS idx_ai_advice_sessions_session_id ON ai_advice_sessions(session_id);
CREATE INDEX IF NOT EXISTS idx_ai_advice_messages_session_id ON ai_advice_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_ai_advice_messages_created_at ON ai_advice_messages(created_at);

-- 验证表是否创建成功
SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'ai_advice_%';
