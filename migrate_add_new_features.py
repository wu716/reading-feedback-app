"""
数据库迁移脚本：添加行为分析和复合指标功能

此脚本将向现有数据库添加以下字段：
1. Action表：action_type, ai_analysis, advice_session_id
2. PracticeLog表：objective_completion, success_score

运行方式：python migrate_add_new_features.py
"""

import sqlite3
import sys
from pathlib import Path

# 数据库路径
DB_PATH = "app.db"


def migrate_database():
    """执行数据库迁移"""
    if not Path(DB_PATH).exists():
        print(f"错误：数据库文件 {DB_PATH} 不存在")
        return False
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        print("开始数据库迁移...")
        
        # 检查并添加Action表的新字段
        print("\n1. 检查Action表...")
        cursor.execute("PRAGMA table_info(actions)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'action_type' not in columns:
            print("  添加 action_type 字段...")
            cursor.execute("""
                ALTER TABLE actions 
                ADD COLUMN action_type VARCHAR(20) DEFAULT 'trigger'
            """)
            print("  ✓ action_type 字段已添加")
        else:
            print("  - action_type 字段已存在，跳过")
        
        if 'ai_analysis' not in columns:
            print("  添加 ai_analysis 字段...")
            cursor.execute("""
                ALTER TABLE actions 
                ADD COLUMN ai_analysis TEXT
            """)
            print("  ✓ ai_analysis 字段已添加")
        else:
            print("  - ai_analysis 字段已存在，跳过")
        
        if 'advice_session_id' not in columns:
            print("  添加 advice_session_id 字段...")
            cursor.execute("""
                ALTER TABLE actions 
                ADD COLUMN advice_session_id VARCHAR(50)
            """)
            print("  ✓ advice_session_id 字段已添加")
        else:
            print("  - advice_session_id 字段已存在，跳过")
        
        # 检查并添加PracticeLog表的新字段
        print("\n2. 检查PracticeLog表...")
        cursor.execute("PRAGMA table_info(practice_logs)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'objective_completion' not in columns:
            print("  添加 objective_completion 字段...")
            cursor.execute("""
                ALTER TABLE practice_logs 
                ADD COLUMN objective_completion FLOAT
            """)
            print("  ✓ objective_completion 字段已添加")
        else:
            print("  - objective_completion 字段已存在，跳过")
        
        if 'success_score' not in columns:
            print("  添加 success_score 字段...")
            cursor.execute("""
                ALTER TABLE practice_logs 
                ADD COLUMN success_score FLOAT
            """)
            print("  ✓ success_score 字段已添加")
        else:
            print("  - success_score 字段已存在，跳过")
        
        # 为现有记录计算success_score
        print("\n3. 为现有记录计算success_score...")
        cursor.execute("""
            SELECT id, result, rating 
            FROM practice_logs 
            WHERE success_score IS NULL
        """)
        logs_to_update = cursor.fetchall()
        
        if logs_to_update:
            print(f"  发现 {len(logs_to_update)} 条需要更新的记录")
            for log_id, result, rating in logs_to_update:
                # 根据result推断客观完成度
                if result == "success":
                    obj_score = 1.0
                elif result == "partial":
                    obj_score = 0.5
                else:
                    obj_score = 0.0
                
                # 主观评分
                if rating:
                    subj_score = (rating - 1) / 4.0
                else:
                    subj_score = obj_score
                
                # 复合指标：60%客观 + 40%主观
                success_score = obj_score * 0.6 + subj_score * 0.4
                
                cursor.execute("""
                    UPDATE practice_logs 
                    SET objective_completion = ?, success_score = ?
                    WHERE id = ?
                """, (obj_score, success_score, log_id))
            
            print(f"  ✓ 已更新 {len(logs_to_update)} 条记录")
        else:
            print("  - 没有需要更新的记录")
        
        # 提交更改
        conn.commit()
        print("\n✓ 数据库迁移成功完成！")
        
        # 显示统计信息
        cursor.execute("SELECT COUNT(*) FROM actions")
        action_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM practice_logs")
        log_count = cursor.fetchone()[0]
        
        print(f"\n数据库统计：")
        print(f"  - 行动项总数: {action_count}")
        print(f"  - 实践记录总数: {log_count}")
        
        conn.close()
        return True
        
    except sqlite3.Error as e:
        print(f"\n✗ 数据库迁移失败: {e}")
        return False
    except Exception as e:
        print(f"\n✗ 发生错误: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("数据库迁移脚本：添加行为分析和复合指标功能")
    print("=" * 60)
    
    success = migrate_database()
    
    if success:
        print("\n迁移完成！现在可以启动应用程序。")
        sys.exit(0)
    else:
        print("\n迁移失败！请检查错误信息。")
        sys.exit(1)

