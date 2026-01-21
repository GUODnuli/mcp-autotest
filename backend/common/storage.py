"""
文件系统存储管理模块

提供统一的文件系统操作接口，包括任务目录管理、文件保存/加载等。
所有文件操作都限制在配置的存储根目录内，防止路径遍历攻击。
"""

import os
import shutil
import json
from pathlib import Path
from typing import Any, Dict, Optional, Union
from datetime import datetime

from .logger import get_logger


class StorageError(Exception):
    """存储操作异常"""
    pass


class StorageManager:
    """文件系统存储管理器"""
    
    def __init__(self, root_path: str = "./storage"):
        """
        初始化存储管理器
        
        Args:
            root_path: 存储根路径
        """
        self.root_path = Path(root_path).resolve()
        self.logger = get_logger()
        
        # 确保根目录存在
        self.root_path.mkdir(parents=True, exist_ok=True)
        
        # 确保子目录存在
        self._ensure_directories()
        
        self.logger.info(f"存储管理器已初始化 | 根路径: {self.root_path}")
    
    def _ensure_directories(self):
        """确保必需的子目录存在"""
        required_dirs = [
            "tasks",
            "templates",
            "vectordb",
            "cache",
            "chat",
        ]
        
        for dir_name in required_dirs:
            dir_path = self.root_path / dir_name
            dir_path.mkdir(parents=True, exist_ok=True)
    
    def _validate_path(self, path: Union[str, Path]) -> Path:
        """
        验证路径安全性（防止路径遍历）
        
        Args:
            path: 待验证的路径
            
        Returns:
            规范化后的绝对路径
            
        Raises:
            StorageError: 路径不安全
        """
        # 转换为绝对路径
        abs_path = Path(path).resolve()
        
        # 检查是否在存储根目录内
        try:
            abs_path.relative_to(self.root_path)
        except ValueError:
            raise StorageError(f"路径 {path} 不在允许的存储范围内")
        
        return abs_path
    
    def create_task_directory(self, task_id: str) -> str:
        """
        创建任务目录结构
        
        Args:
            task_id: 任务 ID
            
        Returns:
            任务目录路径
            
        Raises:
            StorageError: 目录创建失败
        """
        task_dir = self.root_path / "tasks" / task_id
        
        try:
            # 创建主目录
            task_dir.mkdir(parents=True, exist_ok=True)
            
            # 创建子目录
            subdirs = ["documents", "testcases", "reports", "logs"]
            for subdir in subdirs:
                (task_dir / subdir).mkdir(exist_ok=True)
            
            self.logger.info(f"任务目录创建成功 | task_id: {task_id} | 路径: {task_dir}", task_id=task_id)
            return str(task_dir)
        
        except Exception as e:
            raise StorageError(f"创建任务目录失败: {e}")
    
    def get_task_directory(self, task_id: str) -> Optional[str]:
        """
        获取任务目录路径
        
        Args:
            task_id: 任务 ID
            
        Returns:
            任务目录路径，如果不存在则返回 None
        """
        task_dir = self.root_path / "tasks" / task_id
        
        if task_dir.exists():
            return str(task_dir)
        return None
    
    def save_document(
        self,
        task_id: str,
        file_content: bytes,
        filename: str
    ) -> str:
        """
        保存上传的文档
        
        Args:
            task_id: 任务 ID
            file_content: 文件内容
            filename: 文件名
            
        Returns:
            文件保存路径
            
        Raises:
            StorageError: 保存失败
        """
        # 确保任务目录存在
        task_dir = self.get_task_directory(task_id)
        if not task_dir:
            task_dir = self.create_task_directory(task_id)
        
        # 构建文件路径
        file_path = Path(task_dir) / "documents" / filename
        
        try:
            # 验证路径
            safe_path = self._validate_path(file_path)
            
            # 写入文件
            with open(safe_path, 'wb') as f:
                f.write(file_content)
            
            self.logger.info(
                f"文档保存成功 | task_id: {task_id} | 文件: {filename} | 大小: {len(file_content)} bytes",
                task_id=task_id
            )
            return str(safe_path)
        
        except Exception as e:
            raise StorageError(f"保存文档失败: {e}")
    
    def save_testcase(
        self,
        task_id: str,
        testcase_data: Dict[str, Any],
        interface_name: Optional[str] = None
    ) -> str:
        """
        保存生成的测试用例
        
        Args:
            task_id: 任务 ID
            testcase_data: 测试用例数据
            interface_name: 接口名称（用于文件命名）
            
        Returns:
            文件保存路径
            
        Raises:
            StorageError: 保存失败
        """
        # 确保任务目录存在
        task_dir = self.get_task_directory(task_id)
        if not task_dir:
            task_dir = self.create_task_directory(task_id)
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if interface_name:
            # 清理接口名称中的特殊字符
            safe_name = "".join(c if c.isalnum() or c in ['_', '-'] else '_' for c in interface_name)
            filename = f"testcase_{safe_name}_{timestamp}.json"
        else:
            filename = f"testcase_{timestamp}.json"
        
        file_path = Path(task_dir) / "testcases" / filename
        
        try:
            # 验证路径
            safe_path = self._validate_path(file_path)
            
            # 写入 JSON 文件
            with open(safe_path, 'w', encoding='utf-8') as f:
                json.dump(testcase_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(
                f"测试用例保存成功 | task_id: {task_id} | 文件: {filename}",
                task_id=task_id
            )
            return str(safe_path)
        
        except Exception as e:
            raise StorageError(f"保存测试用例失败: {e}")
    
    def save_report(
        self,
        task_id: str,
        report_content: str,
        report_format: str = "md"
    ) -> str:
        """
        保存测试报告
        
        Args:
            task_id: 任务 ID
            report_content: 报告内容
            report_format: 报告格式（md / html）
            
        Returns:
            文件保存路径
            
        Raises:
            StorageError: 保存失败
        """
        # 确保任务目录存在
        task_dir = self.get_task_directory(task_id)
        if not task_dir:
            task_dir = self.create_task_directory(task_id)
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"test_report_{timestamp}.{report_format}"
        
        file_path = Path(task_dir) / "reports" / filename
        
        try:
            # 验证路径
            safe_path = self._validate_path(file_path)
            
            # 写入文件
            with open(safe_path, 'w', encoding='utf-8') as f:
                f.write(report_content)
            
            self.logger.info(
                f"测试报告保存成功 | task_id: {task_id} | 文件: {filename} | 格式: {report_format}",
                task_id=task_id
            )
            return str(safe_path)
        
        except Exception as e:
            raise StorageError(f"保存报告失败: {e}")
    
    def save_log(
        self,
        task_id: str,
        log_content: str,
        log_type: str = "execution"
    ) -> str:
        """
        保存任务执行日志
        
        Args:
            task_id: 任务 ID
            log_content: 日志内容
            log_type: 日志类型
            
        Returns:
            文件保存路径
            
        Raises:
            StorageError: 保存失败
        """
        # 确保任务目录存在
        task_dir = self.get_task_directory(task_id)
        if not task_dir:
            task_dir = self.create_task_directory(task_id)
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{log_type}_{timestamp}.log"
        
        file_path = Path(task_dir) / "logs" / filename
        
        try:
            # 验证路径
            safe_path = self._validate_path(file_path)
            
            # 追加写入文件
            with open(safe_path, 'a', encoding='utf-8') as f:
                f.write(log_content)
            
            return str(safe_path)
        
        except Exception as e:
            raise StorageError(f"保存日志失败: {e}")
    
    def load_file(self, file_path: str) -> bytes:
        """
        加载文件内容
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件内容
            
        Raises:
            StorageError: 加载失败
        """
        try:
            # 验证路径
            safe_path = self._validate_path(file_path)
            
            # 检查文件是否存在
            if not safe_path.exists():
                raise StorageError(f"文件不存在: {file_path}")
            
            # 读取文件
            with open(safe_path, 'rb') as f:
                content = f.read()
            
            self.logger.debug(f"文件加载成功 | 路径: {file_path} | 大小: {len(content)} bytes")
            return content
        
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"加载文件失败: {e}")
    
    def load_json(self, file_path: str) -> Dict[str, Any]:
        """
        加载 JSON 文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            JSON 数据
            
        Raises:
            StorageError: 加载失败
        """
        try:
            content = self.load_file(file_path)
            return json.loads(content.decode('utf-8'))
        except json.JSONDecodeError as e:
            raise StorageError(f"JSON 解析失败: {e}")
    
    def list_files(
        self,
        task_id: str,
        subdir: str = "",
        pattern: str = "*"
    ) -> list[str]:
        """
        列出任务目录下的文件
        
        Args:
            task_id: 任务 ID
            subdir: 子目录（documents / testcases / reports / logs）
            pattern: 文件名模式（支持通配符）
            
        Returns:
            文件路径列表
            
        Raises:
            StorageError: 列出失败
        """
        task_dir = self.get_task_directory(task_id)
        if not task_dir:
            return []
        
        try:
            if subdir:
                search_dir = Path(task_dir) / subdir
            else:
                search_dir = Path(task_dir)
            
            # 验证路径
            safe_dir = self._validate_path(search_dir)
            
            # 列出文件
            files = [str(f) for f in safe_dir.glob(pattern) if f.is_file()]
            return files
        
        except Exception as e:
            raise StorageError(f"列出文件失败: {e}")
    
    def delete_file(self, file_path: str):
        """
        删除文件
        
        Args:
            file_path: 文件路径
            
        Raises:
            StorageError: 删除失败
        """
        try:
            # 验证路径
            safe_path = self._validate_path(file_path)
            
            # 检查文件是否存在
            if not safe_path.exists():
                self.logger.warning(f"文件不存在，无需删除: {file_path}")
                return
            
            # 删除文件
            safe_path.unlink()
            
            self.logger.info(f"文件删除成功 | 路径: {file_path}")
        
        except Exception as e:
            raise StorageError(f"删除文件失败: {e}")
    
    def cleanup_task(
        self,
        task_id: str,
        keep_reports: bool = True
    ):
        """
        清理任务文件
        
        Args:
            task_id: 任务 ID
            keep_reports: 是否保留报告
            
        Raises:
            StorageError: 清理失败
        """
        task_dir = self.get_task_directory(task_id)
        if not task_dir:
            self.logger.warning(f"任务目录不存在，无需清理 | task_id: {task_id}", task_id=task_id)
            return
        
        try:
            task_path = Path(task_dir)
            
            if keep_reports:
                # 只删除非报告文件
                for subdir in ["documents", "testcases", "logs"]:
                    subdir_path = task_path / subdir
                    if subdir_path.exists():
                        shutil.rmtree(subdir_path)
                        subdir_path.mkdir()
                
                self.logger.info(
                    f"任务文件清理完成（保留报告） | task_id: {task_id}",
                    task_id=task_id
                )
            else:
                # 删除整个任务目录
                shutil.rmtree(task_path)
                
                self.logger.info(
                    f"任务目录完全删除 | task_id: {task_id}",
                    task_id=task_id
                )
        
        except Exception as e:
            raise StorageError(f"清理任务文件失败: {e}")
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """
        获取存储统计信息
        
        Returns:
            存储统计数据
        """
        try:
            total_size = 0
            file_count = 0
            
            for root, dirs, files in os.walk(self.root_path):
                for file in files:
                    file_path = Path(root) / file
                    total_size += file_path.stat().st_size
                    file_count += 1
            
            return {
                "root_path": str(self.root_path),
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "file_count": file_count,
                "task_count": len(list((self.root_path / "tasks").iterdir())) if (self.root_path / "tasks").exists() else 0,
            }
        
        except Exception as e:
            self.logger.error(f"获取存储统计失败: {e}")
            return {}
    
    def save_interfaces(
        self,
        task_id: str,
        interfaces: list[Dict[str, Any]]
    ) -> str:
        """
        保存解析的接口列表
        
        Args:
            task_id: 任务 ID
            interfaces: 接口信息列表
            
        Returns:
            文件保存路径
            
        Raises:
            StorageError: 保存失败
        """
        # 确保任务目录存在
        task_dir = self.get_task_directory(task_id)
        if not task_dir:
            task_dir = self.create_task_directory(task_id)
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"interfaces_{timestamp}.json"
        
        file_path = Path(task_dir) / "documents" / filename
        
        try:
            # 验证路径
            safe_path = self._validate_path(file_path)
            
            # 写入 JSON 文件
            with open(safe_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "task_id": task_id,
                    "interface_count": len(interfaces),
                    "interfaces": interfaces,
                    "created_at": datetime.now().isoformat()
                }, f, ensure_ascii=False, indent=2)
            
            self.logger.info(
                f"接口列表保存成功 | task_id: {task_id} | 接口数: {len(interfaces)}",
                task_id=task_id
            )
            return str(safe_path)
        
        except Exception as e:
            raise StorageError(f"保存接口列表失败: {e}")
    
    def load_interfaces(self, task_id: str) -> list[Dict[str, Any]]:
        """
        加载接口列表
        
        Args:
            task_id: 任务 ID
            
        Returns:
            接口信息列表
            
        Raises:
            StorageError: 加载失败
        """
        task_dir = self.get_task_directory(task_id)
        if not task_dir:
            return []
        
        try:
            # 查找最新的接口文件
            interface_files = list((Path(task_dir) / "documents").glob("interfaces_*.json"))
            if not interface_files:
                return []
            
            # 使用最新的文件
            latest_file = max(interface_files, key=lambda f: f.stat().st_mtime)
            
            with open(latest_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return data.get("interfaces", [])
        
        except Exception as e:
            raise StorageError(f"加载接口列表失败: {e}")
    
    def save_testcases(
        self,
        task_id: str,
        interface_name: str,
        testcases: list[Dict[str, Any]]
    ) -> str:
        """
        保存测试用例列表
        
        Args:
            task_id: 任务 ID
            interface_name: 接口名称
            testcases: 测试用例列表
            
        Returns:
            文件保存路径
            
        Raises:
            StorageError: 保存失败
        """
        # 确保任务目录存在
        task_dir = self.get_task_directory(task_id)
        if not task_dir:
            task_dir = self.create_task_directory(task_id)
        
        # 确保 testcases 子目录存在
        testcases_dir = Path(task_dir) / "testcases"
        testcases_dir.mkdir(parents=True, exist_ok=True)
        
        # 清理接口名称中的特殊字符
        safe_name = "".join(c if c.isalnum() or c in ['_', '-'] else '_' for c in interface_name)
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"testcases_{safe_name}_{timestamp}.json"
        
        file_path = Path(task_dir) / "testcases" / filename
        
        try:
            # 验证路径
            safe_path = self._validate_path(file_path)
            
            # 写入 JSON 文件
            with open(safe_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "task_id": task_id,
                    "interface_name": interface_name,
                    "testcase_count": len(testcases),
                    "testcases": testcases,
                    "created_at": datetime.now().isoformat()
                }, f, ensure_ascii=False, indent=2)
            
            self.logger.info(
                f"测试用例保存成功 | task_id: {task_id} | 接口: {interface_name} | 用例数: {len(testcases)}",
                task_id=task_id
            )
            return str(safe_path)
        
        except Exception as e:
            raise StorageError(f"保存测试用例失败: {e}")
    
    def load_testcases(
        self,
        task_id: str,
        interface_name: str
    ) -> list[Dict[str, Any]]:
        """
        加载指定接口的测试用例
        
        Args:
            task_id: 任务 ID
            interface_name: 接口名称
            
        Returns:
            测试用例列表
            
        Raises:
            StorageError: 加载失败
        """
        task_dir = self.get_task_directory(task_id)
        if not task_dir:
            return []
        
        try:
            # 清理接口名称
            safe_name = "".join(c if c.isalnum() or c in ['_', '-'] else '_' for c in interface_name)
            
            # 查找匹配的测试用例文件
            testcase_files = list((Path(task_dir) / "testcases").glob(f"testcases_{safe_name}_*.json"))
            if not testcase_files:
                return []
            
            # 使用最新的文件
            latest_file = max(testcase_files, key=lambda f: f.stat().st_mtime)
            
            with open(latest_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return data.get("testcases", [])
        
        except Exception as e:
            raise StorageError(f"加载测试用例失败: {e}")
    
    def load_all_testcases(self, task_id: str) -> list[Dict[str, Any]]:
        """
        加载任务的所有测试用例
        
        Args:
            task_id: 任务 ID
            
        Returns:
            所有测试用例列表
            
        Raises:
            StorageError: 加载失败
        """
        task_dir = self.get_task_directory(task_id)
        if not task_dir:
            return []
        
        try:
            all_testcases = []
            
            # 查找所有测试用例文件
            testcase_files = list((Path(task_dir) / "testcases").glob("testcases_*.json"))
            
            for file_path in testcase_files:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    all_testcases.extend(data.get("testcases", []))
            
            return all_testcases
        
        except Exception as e:
            raise StorageError(f"加载所有测试用例失败: {e}")
    
    def save_test_report(
        self,
        task_id: str,
        report_data: Dict[str, Any]
    ) -> str:
        """
        保存测试报告（JSON 格式）
        
        Args:
            task_id: 任务 ID
            report_data: 报告数据
            
        Returns:
            文件保存路径
            
        Raises:
            StorageError: 保存失败
        """
        # 确保任务目录存在
        task_dir = self.get_task_directory(task_id)
        if not task_dir:
            task_dir = self.create_task_directory(task_id)
        
        # 确保 reports 子目录存在
        reports_dir = Path(task_dir) / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"test_report_{timestamp}.json"
        
        file_path = reports_dir / filename
        
        try:
            # 验证路径
            safe_path = self._validate_path(file_path)
            
            # 写入 JSON 文件
            with open(safe_path, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2, default=str)
            
            self.logger.info(
                f"测试报告保存成功 | task_id: {task_id} | 文件: {filename}",
                task_id=task_id
            )
            return str(safe_path)
        
        except Exception as e:
            raise StorageError(f"保存测试报告失败: {e}")

    def save_chat_file(
        self,
        user_id: str,
        conversation_id: str,
        filename: str,
        file_content: bytes
    ) -> str:
        """
        保存聊天中上传的文件
        
        Args:
            user_id: 用户 ID
            conversation_id: 会话 ID
            filename: 原始文件名
            file_content: 文件内容
            
        Returns:
            保存后的文件路径
        """
        # 构建目录路径: storage/chat/{user_id}/{conversation_id}
        chat_dir = self.root_path / "chat" / user_id / conversation_id
        chat_dir.mkdir(parents=True, exist_ok=True)
        
        # 分离文件名和后缀
        name_part = Path(filename).stem
        extension = Path(filename).suffix
        
        # 加上下划线和时间戳命名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_filename = f"{name_part}_{timestamp}{extension}"
        
        file_path = chat_dir / new_filename
        
        try:
            # 验证路径安全
            safe_path = self._validate_path(file_path)
            
            with open(safe_path, 'wb') as f:
                f.write(file_content)
                
            self.logger.info(f"聊天文件保存成功 | user_id: {user_id} | conv_id: {conversation_id} | 文件: {new_filename}")
            return str(safe_path)
        except Exception as e:
            raise StorageError(f"保存聊天文件失败: {e}")

    def cleanup_old_files(self, days_to_keep: int = 7):
        """
        清理超过指定天数的旧文件（目前主要清理 chat 目录）
        
        Args:
            days_to_keep: 保留天数
        """
        chat_root = self.root_path / "chat"
        if not chat_root.exists():
            return
            
        import time
        now = time.time()
        seconds_to_keep = days_to_keep * 24 * 3600
        
        count = 0
        try:
            for root, dirs, files in os.walk(chat_root):
                for file in files:
                    file_path = Path(root) / file
                    file_mtime = file_path.stat().st_mtime
                    
                    if now - file_mtime > seconds_to_keep:
                        file_path.unlink()
                        count += 1
                        
            if count > 0:
                self.logger.info(f"成功清理 {count} 个超过 {days_to_keep} 天的旧文件")
        except Exception as e:
            self.logger.error(f"清理旧文件时发生错误: {e}")


# 全局存储管理器实例
_storage_manager: Optional[StorageManager] = None


def get_storage_manager(root_path: str = "./storage") -> StorageManager:
    """
    获取全局存储管理器实例（单例模式）
    
    Args:
        root_path: 存储根路径
        
    Returns:
        存储管理器实例
    """
    global _storage_manager
    if _storage_manager is None:
        _storage_manager = StorageManager(root_path)
    return _storage_manager

