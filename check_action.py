#!/usr/bin/env python3
"""
检查行动项状态的诊断脚本
"""

import sqlite3
import sys

def check_action(action_id):
    """检查指定行动项的状态"""
    db_path = "app.db"
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 查询行动项
        cursor.execute("""
            SELECT id, user_id, action_text, action_type, deleted_at, created_at
            FROM actions
            WHERE id = ?
        """, (action_id,))
        
        result = cursor.fetchone()
        
        if not result:
            print(f"❌ 行动项ID {action_id} 不存在于数据库中")
            return
        
        action_id, user_id, action_text, action_type, deleted_at, created_at = result
        
        print("=" * 60)
        print(f"行动项详情 (ID: {action_id})")
        print("=" * 60)
        print(f"用户ID: {user_id}")
        print(f"行动内容: {action_text}")
        print(f"行动类型: {action_type}")
        print(f"删除状态: {'已删除' if deleted_at else '未删除'}")
        if deleted_at:
            print(f"删除时间: {deleted_at}")
        print(f"创建时间: {created_at}")
        print("=" * 60)
        
        # 检查该用户的所有行动项
        cursor.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN deleted_at IS NULL THEN 1 ELSE 0 END) as active,
                   SUM(CASE WHEN deleted_at IS NOT NULL THEN 1 ELSE 0 END) as deleted
            FROM actions
            WHERE user_id = ?
        """, (user_id,))
        
        total, active, deleted = cursor.fetchone()
        print(f"\n用户 {user_id} 的行动项统计：")
        print(f"  - 总数: {total}")
        print(f"  - 活跃: {active}")
        print(f"  - 已删除: {deleted}")
        
    except Exception as e:
        print(f"❌ 错误: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        action_id = int(sys.argv[1])
    else:
        action_id = 13  # 默认检查ID 13
    
    check_action(action_id)
