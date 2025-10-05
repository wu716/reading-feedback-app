#!/usr/bin/env python3
"""
数据库迁移脚本：添加时间管理字段
运行此脚本将为 Action 表添加时间管理相关字段
"""

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from app.models import Base, Action  # 导入 Base 和 Action 模型

def migrate_database():
    """执行数据库迁移"""
    print("🚀 开始数据库迁移...")
    
    # 直接定义数据库连接
    database_url = "sqlite:///./app.db"
    engine = create_engine(database_url)
    
    try:
        # 第一步：确保 actions 表存在
        print("🔍 检查并创建 actions 表（如果不存在）...")
        Base.metadata.create_all(engine)  # 使用模型创建所有表，包括 actions
        
        # 第二步：检查是否需要添加字段
        with engine.connect() as conn:
            # 检查 duration_type 字段是否已存在
            result = conn.execute(text("""
                SELECT COUNT(*) as count 
                FROM pragma_table_info('actions') 
                WHERE name = 'duration_type'
            """))
            
            if result.fetchone()[0] > 0:
                print("✅ 时间管理字段已存在，无需迁移")
                return
            
            print("📝 添加时间管理字段...")
            
            # 添加新字段
            migration_sql = """
                ALTER TABLE actions ADD COLUMN duration_type VARCHAR(20) DEFAULT 'short_term' NOT NULL;
                ALTER TABLE actions ADD COLUMN target_duration_days INTEGER;
                ALTER TABLE actions ADD COLUMN target_frequency VARCHAR(50);
                ALTER TABLE actions ADD COLUMN custom_frequency_days INTEGER;
                ALTER TABLE actions ADD COLUMN start_date DATE;
                ALTER TABLE actions ADD COLUMN end_date DATE;
            """
            
            # 执行迁移
            for sql in migration_sql.strip().split(';'):
                sql = sql.strip()
                if sql:
                    conn.execute(text(sql))
            
            print("✅ 时间管理字段添加成功")
            
            # 更新现有数据（如果有）
            print("📊 更新现有数据...")
            conn.execute(text("""
                UPDATE actions 
                SET 
                    duration_type = 'short_term',
                    target_duration_days = 30,
                    target_frequency = 'daily',
                    start_date = DATE('now')
                WHERE duration_type IS NULL OR duration_type = ''
            """))
            
            print("✅ 现有数据更新完成")
            
    except Exception as e:
        print(f"❌ 迁移失败: {e}")
        return False
    
    print("🎉 数据库迁移完成！")
    return True

if __name__ == "__main__":
    success = migrate_database()
    sys.exit(0 if success else 1)