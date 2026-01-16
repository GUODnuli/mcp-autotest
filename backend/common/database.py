"""
SQLite 数据库模块

提供任务数据的持久化存储，支持断点续传机制。
包含任务表结构、CRUD 操作、事务支持等功能。
"""

import sqlite3
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from enum import Enum
from contextlib import contextmanager

from .logger import get_logger


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskType(str, Enum):
    """任务类型枚举"""
    GENERATE_TESTCASE = "generate-testcase"
    AUTOTEST = "autotest"
    ANALYZE_REPORT = "analyze-report"


class DatabaseError(Exception):
    """数据库操作异常"""
    pass


class Database:
    """SQLite 数据库管理器"""
    
    def __init__(self, database_path: str = "./storage/tasks.db"):
        """
        初始化数据库管理器
        
        Args:
            database_path: 数据库文件路径
        """
        self.database_path = Path(database_path)
        self.logger = get_logger()
        
        # 确保数据库目录存在
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 初始化数据库
        self._init_database()
        
        self.logger.info(f"数据库已初始化 | 路径: {self.database_path}")
    
    @contextmanager
    def _get_connection(self):
        """
        获取数据库连接（上下文管理器）
        
        Yields:
            数据库连接对象
        """
        conn = sqlite3.connect(
            self.database_path,
            check_same_thread=False,
            timeout=30.0
        )
        # 启用外键约束
        conn.execute("PRAGMA foreign_keys = ON")
        # 返回字典格式的行
        conn.row_factory = sqlite3.Row
        
        try:
            yield conn
        finally:
            conn.close()
    
    def _init_database(self):
        """初始化数据库表结构"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 创建任务表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    task_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    parameters TEXT,
                    result TEXT,
                    checkpoint TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    error_message TEXT
                )
            """)
            
            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_task_type 
                ON tasks(task_type)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_status 
                ON tasks(status)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_created_at 
                ON tasks(created_at)
            """)
            
            conn.commit()
            self.logger.debug("数据库表结构初始化完成")
    
    def create_task(
        self,
        task_id: str,
        task_type: TaskType,
        parameters: Dict[str, Any]
    ) -> bool:
        """
        创建新任务
        
        Args:
            task_id: 任务唯一标识
            task_type: 任务类型
            parameters: 任务参数
            
        Returns:
            是否创建成功
            
        Raises:
            DatabaseError: 创建失败
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                now = datetime.now().isoformat()
                
                cursor.execute("""
                    INSERT INTO tasks (
                        task_id, task_type, status, parameters,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    task_id,
                    task_type.value,
                    TaskStatus.PENDING.value,
                    json.dumps(parameters, ensure_ascii=False),
                    now,
                    now
                ))
                
                conn.commit()
                
                self.logger.info(
                    f"任务创建成功 | task_id: {task_id} | type: {task_type.value}",
                    task_id=task_id
                )
                return True
        
        except sqlite3.IntegrityError:
            self.logger.error(f"任务 ID 已存在: {task_id}", task_id=task_id)
            raise DatabaseError(f"任务 ID 已存在: {task_id}")
        except Exception as e:
            self.logger.error(f"创建任务失败: {e}", task_id=task_id)
            raise DatabaseError(f"创建任务失败: {e}")
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务信息
        
        Args:
            task_id: 任务 ID
            
        Returns:
            任务信息字典，不存在则返回 None
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT * FROM tasks WHERE task_id = ?
                """, (task_id,))
                
                row = cursor.fetchone()
                
                if row:
                    task = dict(row)
                    # 反序列化 JSON 字段
                    if task['parameters']:
                        task['parameters'] = json.loads(task['parameters'])
                    if task['result']:
                        task['result'] = json.loads(task['result'])
                    if task['checkpoint']:
                        task['checkpoint'] = json.loads(task['checkpoint'])
                    
                    return task
                return None
        
        except Exception as e:
            self.logger.error(f"获取任务失败: {e}", task_id=task_id)
            raise DatabaseError(f"获取任务失败: {e}")
    
    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        error_message: Optional[str] = None
    ) -> bool:
        """
        更新任务状态
        
        Args:
            task_id: 任务 ID
            status: 新状态
            error_message: 错误信息（失败时）
            
        Returns:
            是否更新成功
            
        Raises:
            DatabaseError: 更新失败
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                now = datetime.now().isoformat()
                
                # 根据状态设置特定字段
                if status == TaskStatus.RUNNING:
                    cursor.execute("""
                        UPDATE tasks 
                        SET status = ?, updated_at = ?, started_at = ?
                        WHERE task_id = ?
                    """, (status.value, now, now, task_id))
                
                elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                    cursor.execute("""
                        UPDATE tasks 
                        SET status = ?, updated_at = ?, completed_at = ?, error_message = ?
                        WHERE task_id = ?
                    """, (status.value, now, now, error_message, task_id))
                
                else:
                    cursor.execute("""
                        UPDATE tasks 
                        SET status = ?, updated_at = ?, error_message = ?
                        WHERE task_id = ?
                    """, (status.value, now, error_message, task_id))
                
                conn.commit()
                
                self.logger.info(
                    f"任务状态更新 | task_id: {task_id} | status: {status.value}",
                    task_id=task_id
                )
                return cursor.rowcount > 0
        
        except Exception as e:
            self.logger.error(f"更新任务状态失败: {e}", task_id=task_id)
            raise DatabaseError(f"更新任务状态失败: {e}")
    
    def update_task_result(
        self,
        task_id: str,
        result: Dict[str, Any]
    ) -> bool:
        """
        更新任务结果
        
        Args:
            task_id: 任务 ID
            result: 任务结果数据
            
        Returns:
            是否更新成功
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                now = datetime.now().isoformat()
                
                cursor.execute("""
                    UPDATE tasks 
                    SET result = ?, updated_at = ?
                    WHERE task_id = ?
                """, (json.dumps(result, ensure_ascii=False), now, task_id))
                
                conn.commit()
                
                self.logger.debug(f"任务结果更新成功 | task_id: {task_id}", task_id=task_id)
                return cursor.rowcount > 0
        
        except Exception as e:
            self.logger.error(f"更新任务结果失败: {e}", task_id=task_id)
            raise DatabaseError(f"更新任务结果失败: {e}")
    
    def save_checkpoint(
        self,
        task_id: str,
        checkpoint: Dict[str, Any]
    ) -> bool:
        """
        保存任务检查点（用于断点续传）
        
        Args:
            task_id: 任务 ID
            checkpoint: 检查点数据
            
        Returns:
            是否保存成功
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                now = datetime.now().isoformat()
                
                cursor.execute("""
                    UPDATE tasks 
                    SET checkpoint = ?, updated_at = ?
                    WHERE task_id = ?
                """, (json.dumps(checkpoint, ensure_ascii=False), now, task_id))
                
                conn.commit()
                
                self.logger.info(
                    f"检查点保存成功 | task_id: {task_id} | 进度追踪点已更新",
                    task_id=task_id
                )
                return cursor.rowcount > 0
        
        except Exception as e:
            self.logger.error(f"保存检查点失败: {e}", task_id=task_id)
            raise DatabaseError(f"保存检查点失败: {e}")
    
    def get_checkpoint(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务检查点
        
        Args:
            task_id: 任务 ID
            
        Returns:
            检查点数据，不存在则返回 None
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT checkpoint FROM tasks WHERE task_id = ?
                """, (task_id,))
                
                row = cursor.fetchone()
                
                if row and row['checkpoint']:
                    return json.loads(row['checkpoint'])
                return None
        
        except Exception as e:
            self.logger.error(f"获取检查点失败: {e}", task_id=task_id)
            raise DatabaseError(f"获取检查点失败: {e}")
    
    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        task_type: Optional[TaskType] = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "created_at",
        order_dir: str = "desc"
    ) -> List[Dict[str, Any]]:
        """
        列出任务
        
        Args:
            status: 按状态过滤（可选）
            task_type: 按类型过滤（可选）
            limit: 返回数量限制
            offset: 偏移量
            order_by: 排序字段
            order_dir: 排序方向（asc/desc）
            
        Returns:
            任务列表
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                query = "SELECT * FROM tasks WHERE 1=1"
                params = []
                
                if status:
                    query += " AND status = ?"
                    params.append(status.value)
                
                if task_type:
                    query += " AND task_type = ?"
                    params.append(task_type.value)
                
                # 验证排序字段和方向
                valid_order_fields = ["created_at", "updated_at", "task_id", "status"]
                if order_by not in valid_order_fields:
                    order_by = "created_at"
                
                order_dir = "DESC" if order_dir.lower() == "desc" else "ASC"
                
                query += f" ORDER BY {order_by} {order_dir} LIMIT ? OFFSET ?"
                params.extend([limit, offset])
                
                cursor.execute(query, params)
                
                rows = cursor.fetchall()
                
                tasks = []
                for row in rows:
                    task = dict(row)
                    # 反序列化 JSON 字段
                    if task['parameters']:
                        task['parameters'] = json.loads(task['parameters'])
                    if task['result']:
                        task['result'] = json.loads(task['result'])
                    if task['checkpoint']:
                        task['checkpoint'] = json.loads(task['checkpoint'])
                    tasks.append(task)
                
                return tasks
        
        except Exception as e:
            self.logger.error(f"列出任务失败: {e}")
            raise DatabaseError(f"列出任务失败: {e}")
    
    def delete_task(self, task_id: str) -> bool:
        """
        删除任务
        
        Args:
            task_id: 任务 ID
            
        Returns:
            是否删除成功
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    DELETE FROM tasks WHERE task_id = ?
                """, (task_id,))
                
                conn.commit()
                
                if cursor.rowcount > 0:
                    self.logger.info(f"任务删除成功 | task_id: {task_id}", task_id=task_id)
                    return True
                else:
                    self.logger.warning(f"任务不存在 | task_id: {task_id}", task_id=task_id)
                    return False
        
        except Exception as e:
            self.logger.error(f"删除任务失败: {e}", task_id=task_id)
            raise DatabaseError(f"删除任务失败: {e}")
    
    def count_tasks(
        self,
        status: Optional[TaskStatus] = None,
        task_type: Optional[TaskType] = None
    ) -> int:
        """
        统计任务数量
        
        Args:
            status: 按状态过滤（可选）
            task_type: 按类型过滤（可选）
            
        Returns:
            任务数量
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                query = "SELECT COUNT(*) as count FROM tasks WHERE 1=1"
                params = []
                
                if status:
                    query += " AND status = ?"
                    params.append(status.value)
                
                if task_type:
                    query += " AND task_type = ?"
                    params.append(task_type.value)
                
                cursor.execute(query, params)
                result = cursor.fetchone()
                
                return result['count'] if result else 0
        
        except Exception as e:
            self.logger.error(f"统计任务数量失败: {e}")
            return 0
    
    def cleanup_old_tasks(self, retention_days: int = 90) -> int:
        """
        清理过期任务
        
        Args:
            retention_days: 保留天数
            
        Returns:
            删除的任务数量
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 计算截止日期
                cutoff_date = datetime.now()
                cutoff_date = cutoff_date.replace(
                    day=cutoff_date.day - retention_days
                ).isoformat()
                
                # 删除已完成或失败的过期任务
                cursor.execute("""
                    DELETE FROM tasks 
                    WHERE status IN (?, ?, ?) 
                    AND created_at < ?
                """, (
                    TaskStatus.COMPLETED.value,
                    TaskStatus.FAILED.value,
                    TaskStatus.CANCELLED.value,
                    cutoff_date
                ))
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                if deleted_count > 0:
                    self.logger.info(f"清理过期任务完成 | 删除数量: {deleted_count}")
                
                return deleted_count
        
        except Exception as e:
            self.logger.error(f"清理过期任务失败: {e}")
            raise DatabaseError(f"清理过期任务失败: {e}")
    
    def get_task_statistics(self) -> Dict[str, Any]:
        """
        获取任务统计信息
        
        Returns:
            统计数据字典
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 总任务数
                cursor.execute("SELECT COUNT(*) as count FROM tasks")
                total_count = cursor.fetchone()['count']
                
                # 各状态任务数
                cursor.execute("""
                    SELECT status, COUNT(*) as count 
                    FROM tasks 
                    GROUP BY status
                """)
                status_counts = {row['status']: row['count'] for row in cursor.fetchall()}
                
                # 各类型任务数
                cursor.execute("""
                    SELECT task_type, COUNT(*) as count 
                    FROM tasks 
                    GROUP BY task_type
                """)
                type_counts = {row['task_type']: row['count'] for row in cursor.fetchall()}
                
                return {
                    "total_count": total_count,
                    "status_counts": status_counts,
                    "type_counts": type_counts,
                }
        
        except Exception as e:
            self.logger.error(f"获取任务统计失败: {e}")
            return {}


# 全局数据库实例
_database: Optional[Database] = None


def get_database(database_path: str = "./storage/tasks.db") -> Database:
    """
    获取全局数据库实例（单例模式）
    
    Args:
        database_path: 数据库文件路径
        
    Returns:
        数据库实例
    """
    global _database
    if _database is None:
        _database = Database(database_path)
    return _database
