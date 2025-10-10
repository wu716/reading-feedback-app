#!/usr/bin/env python3
"""
简化的数据库迁移脚本：添加attempt_number字段
"""

import sqlite3
import os

def main():
    db_path = "app.db"
    
    if not os.path.exists(db_path):
        print(f"数据库文件 {db_path} 不存在")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("开始添加attempt_number字段...")
        
        # 检查字段是否已存在
        cursor.execute("PRAGMA table_info(practice_logs)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'attempt_number' in columns:
            print("attempt_number 字段已存在")
        else:
            cursor.execute("ALTER TABLE practice_logs ADD COLUMN attempt_number INTEGER")
            print("attempt_number 字段已添加")
        
        conn.commit()
        print("迁移完成！")
        
    except Exception as e:
        print(f"错误: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()
