# -*- coding: utf-8 -*-
"""
Self-talk 提醒功能数据库迁移脚本
"""
import sqlite3
import sys
import os
from datetime import datetime

DB_PATH = "app.db"

def migrate_database():
    """执行数据库迁移"""
    print("=" * 50)
    print("Self-talk 提醒功能数据库迁移")
    print("=" * 50)
    
    if not os.path.exists(DB_PATH):
        print(f"❌ 数据库文件不存在: {DB_PATH}")
        return False
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 检查表是否已存在
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='self_talk_reminder_settings'
        """)
        
        if cursor.fetchone():
            print("⚠️  提醒设置表已存在，跳过创建")
        else:
            print("\n1. 创建 self_talk_reminder_settings 表...")
            cursor.execute("""
                CREATE TABLE self_talk_reminder_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE,
                    is_enabled BOOLEAN DEFAULT 1,
                    
                    -- 时间型提醒
                    daily_reminder_enabled BOOLEAN DEFAULT 0,
                    daily_reminder_time VARCHAR(8),
                    reminder_days TEXT DEFAULT '[0,1,2,3,4,5,6]',
                    
                    -- 行为触发型提醒
                    after_action_reminder BOOLEAN DEFAULT 1,
                    after_new_action_reminder BOOLEAN DEFAULT 1,
                    inactive_days_threshold INTEGER DEFAULT 3,
                    
                    -- 通知方式
                    browser_notification BOOLEAN DEFAULT 1,
                    email_notification BOOLEAN DEFAULT 1,
                    
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP,
                    
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
            print("✅ self_talk_reminder_settings 表创建成功")
        
        # 检查日志表是否已存在
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='self_talk_reminder_logs'
        """)
        
        if cursor.fetchone():
            print("⚠️  提醒日志表已存在，跳过创建")
        else:
            print("\n2. 创建 self_talk_reminder_logs 表...")
            cursor.execute("""
                CREATE TABLE self_talk_reminder_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    reminder_type VARCHAR(50) NOT NULL,
                    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    dismissed_at TIMESTAMP,
                    action_taken BOOLEAN DEFAULT 0,
                    notification_method VARCHAR(20),
                    
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
            print("✅ self_talk_reminder_logs 表创建成功")
        
        # 创建索引
        print("\n3. 创建索引...")
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_reminder_settings_user 
                ON self_talk_reminder_settings(user_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_reminder_logs_user 
                ON self_talk_reminder_logs(user_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_reminder_logs_triggered 
                ON self_talk_reminder_logs(triggered_at)
            """)
            print("✅ 索引创建成功")
        except Exception as e:
            print(f"⚠️  索引创建警告: {e}")
        
        # 提交更改
        conn.commit()
        
        print("\n" + "=" * 50)
        print("✅ 数据库迁移成功完成！")
        print("=" * 50)
        
        # 显示表信息
        print("\n📊 数据库表信息:")
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' 
            AND name LIKE '%self_talk%'
            ORDER BY name
        """)
        tables = cursor.fetchall()
        for table in tables:
            print(f"  - {table[0]}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def rollback_migration():
    """回滚迁移（删除表）"""
    print("\n⚠️  警告：这将删除 self_talk 提醒相关的所有表和数据！")
    confirm = input("确认回滚？(yes/no): ")
    
    if confirm.lower() != 'yes':
        print("❌ 回滚已取消")
        return False
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        print("\n删除表...")
        cursor.execute("DROP TABLE IF EXISTS self_talk_reminder_logs")
        cursor.execute("DROP TABLE IF EXISTS self_talk_reminder_settings")
        
        conn.commit()
        conn.close()
        
        print("✅ 回滚成功")
        return True
        
    except Exception as e:
        print(f"❌ 回滚失败: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback_migration()
    else:
        migrate_database()

