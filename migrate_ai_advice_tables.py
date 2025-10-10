#!/usr/bin/env python3
"""
AI建议功能数据库迁移脚本
创建AI建议会话和消息表
"""

import sqlite3
import os
from datetime import datetime

def migrate_database():
    """执行数据库迁移"""
    
    db_path = "app.db"
    
    if not os.path.exists(db_path):
        print(f"❌ 数据库文件 {db_path} 不存在")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("🔄 开始创建AI建议相关表...")
        
        # 创建AI建议会话表
        cursor.execute("""
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
            )
        """)
        
        # 创建AI建议消息表
        cursor.execute("""
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
            )
        """)
        
        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_advice_sessions_user_id ON ai_advice_sessions(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_advice_sessions_action_id ON ai_advice_sessions(action_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_advice_sessions_session_id ON ai_advice_sessions(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_advice_messages_session_id ON ai_advice_messages(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_advice_messages_created_at ON ai_advice_messages(created_at)")
        
        conn.commit()
        print("✅ AI建议相关表创建成功")
        
        # 验证表是否创建成功
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'ai_advice_%'")
        tables = cursor.fetchall()
        
        print(f"📋 已创建的表: {[table[0] for table in tables]}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ 迁移失败: {e}")
        if 'conn' in locals():
            conn.close()
        return False

if __name__ == "__main__":
    print("🚀 开始AI建议功能数据库迁移...")
    success = migrate_database()
    
    if success:
        print("🎉 迁移完成！")
    else:
        print("💥 迁移失败！")
        exit(1)
