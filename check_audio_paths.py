#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查数据库中的音频路径
"""
import sqlite3
import os

def check_audio_paths():
    try:
        conn = sqlite3.connect('app.db')
        cursor = conn.cursor()
        
        # 查询最近的 self_talks 记录
        cursor.execute("""
            SELECT id, audio_path, created_at 
            FROM self_talks 
            WHERE deleted_at IS NULL 
            ORDER BY id DESC 
            LIMIT 5
        """)
        
        records = cursor.fetchall()
        
        print("数据库中的音频路径:")
        print("-" * 80)
        
        for record in records:
            record_id, audio_path, created_at = record
            print(f"ID: {record_id}")
            print(f"创建时间: {created_at}")
            print(f"音频路径: {repr(audio_path)}")
            print(f"路径长度: {len(audio_path)}")
            print(f"字符码: {[ord(c) for c in audio_path]}")
            
            # 检查文件是否存在
            if os.path.exists(audio_path):
                print(f"文件存在: ✅")
                print(f"文件大小: {os.path.getsize(audio_path)} bytes")
            else:
                print(f"文件存在: ❌")
                
            print("-" * 80)
        
        conn.close()
        
    except Exception as e:
        print(f"查询失败: {e}")

if __name__ == "__main__":
    check_audio_paths()
