"""
取消指定任务的 Python 脚本
"""
import sqlite3
from datetime import datetime
from pathlib import Path

# 数据库路径
DB_PATH = Path(__file__).parent.parent / "storage" / "tasks.db"
TASK_ID = "	50e04607-a37c-4308-942d-39e4b4aab7dd"

def cancel_task(task_id: str):
    """取消任务"""
    try:
        # 连接数据库
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 更新任务状态
        cursor.execute("""
            UPDATE tasks 
            SET 
                status = 'CANCELLED',
                updated_at = ?,
                error_message = '手动取消任务'
            WHERE 
                task_id = ?
        """, (datetime.now().isoformat(), task_id))
        
        # 提交更改
        conn.commit()
        
        # 验证更新结果
        cursor.execute("""
            SELECT 
                task_id,
                task_type,
                status,
                created_at,
                updated_at,
                error_message
            FROM tasks 
            WHERE task_id = ?
        """, (task_id,))
        
        result = cursor.fetchone()
        
        if result:
            print(f"✅ 任务已取消！")
            print(f"任务 ID: {result['task_id']}")
            print(f"任务类型: {result['task_type']}")
            print(f"当前状态: {result['status']}")
            print(f"更新时间: {result['updated_at']}")
            print(f"错误信息: {result['error_message']}")
        else:
            print(f"❌ 未找到任务: {task_id}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ 取消任务失败: {e}")

if __name__ == "__main__":
    print(f"正在取消任务: {TASK_ID}")
    print(f"数据库路径: {DB_PATH}")
    print("-" * 50)
    cancel_task(TASK_ID)
