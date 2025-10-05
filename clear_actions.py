import sqlite3

def clear_actions_table():
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM actions")
        conn.commit()
        print("✅ actions 表已清空")
    except Exception as e:
        print(f"❌ 清空失败: {e}")
    finally:
        conn.close()

def clear_practice_logs_table():
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM practice_logs")
        conn.commit()
        print("✅ practice_logs 表已清空")
    except Exception as e:
        print(f"❌ 清空失败: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    clear_actions_table()
    clear_practice_logs_table()  # 清空实践记录，这样成功率就会是 0%