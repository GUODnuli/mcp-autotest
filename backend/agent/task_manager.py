"""
任务管理器

负责任务生命周期管理、状态机控制和断点续传机制。
"""

import json
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime
from pathlib import Path

from backend.common.logger import Logger
from backend.common.database import Database, TaskStatus, TaskType
from backend.common.storage import StorageManager


class TaskState(str, Enum):
    """任务状态（状态机）"""
    CREATED = "created"  # 已创建
    PARSING_DOC = "parsing_doc"  # 解析文档中
    GENERATING_TESTCASES = "generating_testcases"  # 生成测试用例中
    EXECUTING_TESTS = "executing_tests"  # 执行测试中
    GENERATING_REPORT = "generating_report"  # 生成报告中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败
    CANCELLED = "cancelled"  # 已取消


class TaskManager:
    """
    任务管理器
    
    功能：
    - 任务生命周期管理（创建、启动、暂停、恢复、取消）
    - 状态机控制（状态转换和验证）
    - 断点续传机制（检查点保存/恢复）
    - 任务查询和统计
    - 错误处理和回滚
    
    状态转换规则：
    CREATED → PARSING_DOC → GENERATING_TESTCASES → EXECUTING_TESTS → 
    GENERATING_REPORT → COMPLETED
    
    任何状态都可以转换到 FAILED 或 CANCELLED
    FAILED/CANCELLED 状态可以通过重试回到之前的检查点
    """
    
    def __init__(self, logger: Logger, database: Database, storage: StorageManager):
        self.logger = logger
        self.database = database
        self.storage = storage
        
        # 状态转换映射（定义合法的状态转换）
        self.state_transitions: Dict[TaskState, List[TaskState]] = {
            TaskState.CREATED: [
                TaskState.PARSING_DOC,
                TaskState.CANCELLED
            ],
            TaskState.PARSING_DOC: [
                TaskState.GENERATING_TESTCASES,
                TaskState.FAILED,
                TaskState.CANCELLED
            ],
            TaskState.GENERATING_TESTCASES: [
                TaskState.EXECUTING_TESTS,
                TaskState.FAILED,
                TaskState.CANCELLED
            ],
            TaskState.EXECUTING_TESTS: [
                TaskState.GENERATING_REPORT,
                TaskState.FAILED,
                TaskState.CANCELLED
            ],
            TaskState.GENERATING_REPORT: [
                TaskState.COMPLETED,
                TaskState.FAILED,
                TaskState.CANCELLED
            ],
            TaskState.COMPLETED: [],  # 终止状态
            TaskState.FAILED: [
                TaskState.PARSING_DOC,  # 支持从失败点重试
                TaskState.GENERATING_TESTCASES,
                TaskState.EXECUTING_TESTS,
                TaskState.GENERATING_REPORT
            ],
            TaskState.CANCELLED: []  # 终止状态
        }
        
        # 状态处理器（每个状态的处理函数）
        self.state_handlers: Dict[TaskState, Optional[Callable]] = {}
        
        self.logger.info(
            "TaskManager 初始化完成 | "
            f"支持状态: {[s.value for s in TaskState]}",
            component="TaskManager"
        )
    
    def create_task(
        self,
        task_type: TaskType,
        document_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None  # 可选：如果已有task_id，使用它
    ) -> str:
        """
        创建新任务
        
        Args:
            task_type: 任务类型
            document_path: 文档路径（可选）
            metadata: 元数据（可选）
            task_id: 任务ID（可选，如果已有则使用）
            
        Returns:
            任务ID
        """
        # 生成或使用已有的任务ID
        if not task_id:
            import uuid
            task_id = str(uuid.uuid4())
        
        # 准备参数
        parameters = metadata or {}
        if document_path:
            parameters['document_path'] = document_path
        
        # 创建任务
        self.database.create_task(
            task_id=task_id,
            task_type=task_type,
            parameters=parameters
        )
        
        # 初始化检查点
        self._save_checkpoint(task_id, TaskState.CREATED, {
            "created_at": datetime.now().isoformat(),
            "task_type": task_type.value,
            "document_path": document_path
        })
        
        self.logger.info(
            f"任务已创建 | "
            f"task_id: {task_id} | "
            f"类型: {task_type.value} | "
            f"文档: {document_path}",
            task_id=task_id,
            task_type=task_type.value
        )
        
        return task_id
    
    def get_task_state(self, task_id: str) -> Optional[TaskState]:
        """
        获取任务当前状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务状态
        """
        checkpoint = self.database.get_checkpoint(task_id)
        if checkpoint and "current_state" in checkpoint:
            return TaskState(checkpoint["current_state"])
        return None
    
    def transition_state(
        self,
        task_id: str,
        target_state: TaskState,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        执行状态转换
        
        Args:
            task_id: 任务ID
            target_state: 目标状态
            context: 上下文数据（保存到检查点）
            
        Returns:
            转换是否成功
        """
        current_state = self.get_task_state(task_id)
        
        if current_state is None:
            self.logger.error(
                f"任务状态未找到 | task_id: {task_id}",
                task_id=task_id
            )
            return False
        
        # 验证状态转换是否合法
        if not self._is_valid_transition(current_state, target_state):
            self.logger.error(
                f"非法状态转换 | "
                f"task_id: {task_id} | "
                f"从 {current_state} 到 {target_state}",
                task_id=task_id,
                from_state=current_state,
                to_state=target_state
            )
            return False
        
        # 执行转换
        self._save_checkpoint(task_id, target_state, context or {})
        
        # 更新数据库状态
        self._update_database_status(task_id, target_state)
        
        self.logger.info(
            f"状态转换成功 | "
            f"task_id: {task_id} | "
            f"{current_state} → {target_state}",
            task_id=task_id,
            from_state=current_state,
            to_state=target_state
        )
        
        return True
    
    def restore_from_checkpoint(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        从检查点恢复任务（断点续传）
        
        Args:
            task_id: 任务ID
            
        Returns:
            检查点数据
        """
        checkpoint = self.database.get_checkpoint(task_id)
        
        if not checkpoint:
            self.logger.warning(
                f"检查点未找到 | task_id: {task_id}",
                task_id=task_id
            )
            return None
        
        current_state = checkpoint.get("current_state")
        
        self.logger.info(
            f"从检查点恢复任务 | "
            f"task_id: {task_id} | "
            f"状态: {current_state}",
            task_id=task_id,
            state=current_state
        )
        
        return checkpoint
    
    def retry_task(self, task_id: str) -> bool:
        """
        重试失败的任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            重试是否成功启动
        """
        current_state = self.get_task_state(task_id)
        
        if current_state != TaskState.FAILED:
            self.logger.warning(
                f"只能重试失败的任务 | task_id: {task_id} | 当前状态: {current_state}",
                task_id=task_id
            )
            return False
        
        # 获取失败前的状态
        checkpoint = self.database.get_checkpoint(task_id)
        failed_at_state = checkpoint.get("failed_at_state")
        
        if not failed_at_state:
            self.logger.error(
                f"无法确定失败点 | task_id: {task_id}",
                task_id=task_id
            )
            return False
        
        # 恢复到失败前的状态
        retry_state = TaskState(failed_at_state)
        success = self.transition_state(
            task_id,
            retry_state,
            {"retry_at": datetime.now().isoformat()}
        )
        
        if success:
            self.logger.info(
                f"任务重试已启动 | task_id: {task_id} | 从状态: {retry_state}",
                task_id=task_id,
                retry_state=retry_state
            )
        
        return success
    
    def cancel_task(self, task_id: str, reason: Optional[str] = None) -> bool:
        """
        取消任务
        
        Args:
            task_id: 任务ID
            reason: 取消原因（可选）
            
        Returns:
            取消是否成功
        """
        current_state = self.get_task_state(task_id)
        
        if current_state in [TaskState.COMPLETED, TaskState.CANCELLED]:
            self.logger.warning(
                f"任务已处于终止状态，无法取消 | task_id: {task_id} | 状态: {current_state}",
                task_id=task_id
            )
            return False
        
        success = self.transition_state(
            task_id,
            TaskState.CANCELLED,
            {
                "cancelled_at": datetime.now().isoformat(),
                "reason": reason
            }
        )
        
        if success:
            self.logger.info(
                f"任务已取消 | task_id: {task_id} | 原因: {reason}",
                task_id=task_id,
                reason=reason
            )
        
        return success
    
    def mark_task_failed(
        self,
        task_id: str,
        error: str,
        failed_at_state: Optional[TaskState] = None
    ) -> bool:
        """
        标记任务为失败状态
        
        Args:
            task_id: 任务ID
            error: 错误信息
            failed_at_state: 失败时的状态（用于重试）
            
        Returns:
            标记是否成功
        """
        context = {
            "failed_at": datetime.now().isoformat(),
            "error": error
        }
        
        if failed_at_state:
            context["failed_at_state"] = failed_at_state.value
        
        # 先检查任务状态是否存在
        current_state = self.get_task_state(task_id)
        if current_state is None:
            # 如果状态不存在，直接保存失败状态
            self._save_checkpoint(task_id, TaskState.FAILED, context)
            self._update_database_status(task_id, TaskState.FAILED)
            self.logger.error(
                f"任务标记为失败 | task_id: {task_id} | 错误: {error}",
                task_id=task_id,
                error=error
            )
            return True
        
        success = self.transition_state(task_id, TaskState.FAILED, context)
        
        if success:
            self.logger.error(
                f"任务标记为失败 | task_id: {task_id} | 错误: {error}",
                task_id=task_id,
                error=error
            )
        
        return success
    
    def get_task_info(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务详细信息
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务信息
        """
        task = self.database.get_task(task_id)
        if not task:
            return None
        
        checkpoint = self.database.get_checkpoint(task_id)
        
        # 从 parameters 中获取 document_path
        parameters = task.get("parameters", {})
        if isinstance(parameters, str):
            import json
            try:
                parameters = json.loads(parameters)
            except:
                parameters = {}
        
        return {
            "task_id": task_id,
            "type": task.get("type"),
            "status": task.get("status"),
            "current_state": checkpoint.get("current_state") if checkpoint else None,
            "created_at": task.get("created_at"),
            "updated_at": task.get("updated_at"),
            "document_path": parameters.get("document_path"),  # 从 parameters 获取
            "metadata": task.get("metadata", {}),
            "checkpoint": checkpoint
        }
    
    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        task_type: Optional[TaskType] = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str = "created_at",
        order_dir: str = "desc"
    ) -> List[Dict[str, Any]]:
        """
        列出任务列表
        
        Args:
            status: 筛选状态（可选）
            task_type: 筛选类型（可选）
            limit: 最大数量
            offset: 偏移量（用于分页）
            order_by: 排序字段
            order_dir: 排序方向（asc/desc）
            
        Returns:
            任务列表
        """
        tasks = self.database.list_tasks(
            status=status,
            task_type=task_type,
            limit=limit,
            offset=offset,
            order_by=order_by,
            order_dir=order_dir
        )
        
        result = []
        for t in tasks:
            # 获取检查点信息以显示当前步骤
            checkpoint = self.database.get_checkpoint(t["task_id"])
            current_state = checkpoint.get("current_state") if checkpoint else None
            
            result.append({
                "task_id": t["task_id"],
                "type": t.get("task_type"),
                "status": t["status"],
                "current_state": current_state,
                "document_path": t.get("parameters", {}).get("document_path") if t.get("parameters") else None,
                "created_at": t["created_at"],
                "updated_at": t["updated_at"]
            })
        
        return result
    
    def get_task_statistics(self) -> Dict[str, Any]:
        """
        获取任务统计信息
        
        Returns:
            统计数据
        """
        all_tasks = self.database.list_tasks(limit=10000)
        
        stats = {
            "total": len(all_tasks),
            "by_status": {},
            "by_type": {},
            "by_state": {}
        }
        
        for task in all_tasks:
            # 按状态统计
            status = task.get("status", "unknown")
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
            
            # 按类型统计
            task_type = task.get("type", "unknown")
            stats["by_type"][task_type] = stats["by_type"].get(task_type, 0) + 1
            
            # 按状态机状态统计
            checkpoint = self.database.get_checkpoint(task["task_id"])
            if checkpoint and "current_state" in checkpoint:
                state = checkpoint["current_state"]
                stats["by_state"][state] = stats["by_state"].get(state, 0) + 1
        
        return stats
    
    def delete_task(self, task_id: str) -> bool:
        """
        删除任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            删除是否成功
        """
        try:
            # 检查任务状态，只能删除已完成、失败或取消的任务
            task = self.database.get_task(task_id)
            if not task:
                self.logger.warning(f"任务不存在 | task_id: {task_id}", task_id=task_id)
                return False
            
            task_status = TaskStatus(task["status"])
            if task_status == TaskStatus.RUNNING:
                self.logger.warning(
                    f"不能删除运行中的任务 | task_id: {task_id} | 状态: {task_status}",
                    task_id=task_id
                )
                return False
            
            # 删除数据库记录
            success = self.database.delete_task(task_id)
            
            if success:
                # 删除任务文件（可选）
                try:
                    self.storage.cleanup_task(task_id, keep_reports=False)
                except Exception as e:
                    self.logger.warning(f"清理任务文件失败: {e}", task_id=task_id)
                
                self.logger.info(f"任务已删除 | task_id: {task_id}", task_id=task_id)
            
            return success
        except Exception as e:
            self.logger.error(f"删除任务失败: {e}", task_id=task_id, exc_info=True)
            return False
    
    def count_tasks(
        self,
        status: Optional[TaskStatus] = None,
        task_type: Optional[TaskType] = None
    ) -> int:
        """
        统计任务数量
        
        Args:
            status: 筛选状态（可选）
            task_type: 筛选类型（可选）
            
        Returns:
            任务数量
        """
        return self.database.count_tasks(status=status, task_type=task_type)
    
    def register_state_handler(
        self,
        state: TaskState,
        handler: Callable[[str, Dict[str, Any]], bool]
    ):
        """
        注册状态处理器
        
        Args:
            state: 状态
            handler: 处理函数 (task_id, context) -> success
        """
        self.state_handlers[state] = handler
        self.logger.debug(
            f"状态处理器已注册 | 状态: {state}",
            state=state
        )
    
    def execute_state_handler(
        self,
        task_id: str,
        state: TaskState,
        context: Dict[str, Any]
    ) -> bool:
        """
        执行状态处理器
        
        Args:
            task_id: 任务ID
            state: 状态
            context: 上下文
            
        Returns:
            执行是否成功
        """
        handler = self.state_handlers.get(state)
        
        if not handler:
            self.logger.warning(
                f"状态处理器未注册 | 状态: {state}",
                state=state
            )
            return False
        
        try:
            return handler(task_id, context)
        except Exception as e:
            self.logger.error(
                f"状态处理器执行失败 | "
                f"状态: {state} | "
                f"错误: {str(e)}",
                state=state,
                error=str(e),
                exc_info=True
            )
            return False
    
    def _is_valid_transition(
        self,
        from_state: TaskState,
        to_state: TaskState
    ) -> bool:
        """
        验证状态转换是否合法
        
        Args:
            from_state: 起始状态
            to_state: 目标状态
            
        Returns:
            是否合法
        """
        valid_targets = self.state_transitions.get(from_state, [])
        return to_state in valid_targets
    
    def _save_checkpoint(
        self,
        task_id: str,
        state: TaskState,
        context: Dict[str, Any]
    ):
        """
        保存检查点
        
        Args:
            task_id: 任务ID
            state: 当前状态
            context: 上下文数据
        """
        checkpoint = {
            "current_state": state.value,
            "last_updated": datetime.now().isoformat(),
            **context
        }
        
        self.database.save_checkpoint(task_id, checkpoint)
        
        self.logger.debug(
            f"检查点已保存 | task_id: {task_id} | 状态: {state}",
            task_id=task_id,
            state=state
        )
    
    def _update_database_status(self, task_id: str, state: TaskState):
        """
        更新数据库中的任务状态
        
        Args:
            task_id: 任务ID
            state: 状态机状态
        """
        # 将状态机状态映射到数据库状态
        status_mapping = {
            TaskState.CREATED: TaskStatus.PENDING,
            TaskState.PARSING_DOC: TaskStatus.RUNNING,
            TaskState.GENERATING_TESTCASES: TaskStatus.RUNNING,
            TaskState.EXECUTING_TESTS: TaskStatus.RUNNING,
            TaskState.GENERATING_REPORT: TaskStatus.RUNNING,
            TaskState.COMPLETED: TaskStatus.COMPLETED,
            TaskState.FAILED: TaskStatus.FAILED,
            TaskState.CANCELLED: TaskStatus.CANCELLED
        }
        
        db_status = status_mapping.get(state, TaskStatus.PENDING)
        self.database.update_task_status(task_id, db_status)
