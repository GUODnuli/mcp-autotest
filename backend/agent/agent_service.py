"""
Agent HTTP 服务

提供 RESTful API 和 WebSocket 实时推送。
"""

import asyncio
from typing import Any, Dict, List, Optional
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.agent.task_manager import TaskManager, TaskState
from backend.agent.workflow_orchestrator import WorkflowOrchestrator
from backend.common.logger import Logger
from backend.common.database import TaskType, TaskStatus


# 请求/响应模型
class CreateTaskRequest(BaseModel):
    task_type: str
    document_path: Optional[str] = None
    task_id: Optional[str] = None  # 可选：如果上传时生成了task_id，可以传入
    config: Optional[Dict[str, Any]] = None


class TaskResponse(BaseModel):
    success: bool
    task_id: Optional[str] = None
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class AgentService:
    """
    Agent HTTP 服务
    
    功能：
    - RESTful API（任务管理、状态查询、报告下载）
    - WebSocket 实时推送（任务进度、日志）
    - 文件上传处理
    - CORS 支持
    """
    
    def __init__(
        self,
        task_manager: TaskManager,
        workflow_orchestrator: WorkflowOrchestrator,
        logger: Logger,
        config: Dict[str, Any]
    ):
        self.task_manager = task_manager
        self.workflow_orchestrator = workflow_orchestrator
        self.logger = logger
        self.config = config
        
        # 创建 FastAPI 应用
        self.app = FastAPI(
            title="MCP 接口测试智能体 API",
            description="接口测试自动化服务",
            version="1.0.0"
        )
        
        # 配置 CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=config.get("cors_origins", ["*"]),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"]
        )
        
        # WebSocket 连接管理
        self.ws_connections: List[WebSocket] = []
        
        # 注册路由
        self._register_routes()
        
        self.logger.info(
            "AgentService 初始化完成 | "
            f"CORS: {config.get('cors_origins', ['*'])}",
            component="AgentService"
        )
    
    def _register_routes(self):
        """注册 API 路由"""
        
        @self.app.get("/")
        async def root():
            """根路径"""
            return {
                "service": "MCP 接口测试智能体",
                "version": "1.0.0",
                "status": "running"
            }
        
        @self.app.post("/api/tasks", response_model=TaskResponse)
        async def create_task(request: CreateTaskRequest):
            """创建新任务"""
            try:
                self.logger.info(
                    f"[创建任务] 收到请求 | task_type: {request.task_type} | document_path: {request.document_path} | task_id: {request.task_id}",
                    task_type=request.task_type,
                    document_path=request.document_path,
                    task_id=request.task_id
                )
                
                task_type = TaskType(request.task_type)
                
                # 如果上传时已经生成了task_id，使用它；否则生成新的
                if request.task_id:
                    task_id = request.task_id
                    # 直接创建任务记录（使用已存在的task_id）
                    self.task_manager.create_task(
                        task_type=task_type,
                        document_path=request.document_path,
                        task_id=task_id
                    )
                else:
                    # 生成新的task_id
                    task_id = self.task_manager.create_task(
                        task_type=task_type,
                        document_path=request.document_path
                    )
                
                self.logger.info(
                    f"[创建任务] 任务创建成功 | task_id: {task_id}",
                    task_id=task_id
                )
                
                # 异步执行工作流
                if request.document_path:
                    self.logger.info(
                        f"[创建任务] 启动异步工作流 | task_id: {task_id}",
                        task_id=task_id
                    )
                    asyncio.create_task(
                        self._execute_workflow_async(
                            task_id,
                            request.document_path,
                            request.config
                        )
                    )
                
                response = TaskResponse(
                    success=True,
                    task_id=task_id,
                    message="任务已创建"
                )
                
                self.logger.info(
                    f"[创建任务] 返回响应 | success: {response.success} | task_id: {response.task_id}",
                    task_id=task_id
                )
                
                return response
            
            except Exception as e:
                self.logger.error(f"创建任务失败: {str(e)}", exc_info=True)
                return TaskResponse(
                    success=False,
                    message=f"创建任务失败: {str(e)}"
                )
        
        @self.app.get("/api/tasks/{task_id}", response_model=TaskResponse)
        async def get_task(task_id: str):
            """获取任务信息"""
            try:
                self.logger.info(
                    f"[获取任务] 收到请求 | task_id: {task_id}",
                    task_id=task_id
                )
                
                task_info = self.task_manager.get_task_info(task_id)
                
                if not task_info:
                    self.logger.warning(
                        f"[获取任务] 任务不存在 | task_id: {task_id}",
                        task_id=task_id
                    )
                    raise HTTPException(status_code=404, detail="任务不存在")
                
                self.logger.info(
                    f"[获取任务] 任务找到 | task_id: {task_id} | status: {task_info.get('status')}",
                    task_id=task_id,
                    status=task_info.get('status')
                )
                
                return TaskResponse(
                    success=True,
                    data=task_info
                )
            
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"获取任务失败: {str(e)}", exc_info=True)
                return TaskResponse(
                    success=False,
                    message=f"获取任务失败: {str(e)}"
                )
        
        @self.app.get("/api/tasks", response_model=TaskResponse)
        async def list_tasks(
            status: Optional[str] = None,
            task_type: Optional[str] = None,
            page: int = 1,
            page_size: int = 20,
            order_by: str = "created_at",
            order_dir: str = "desc"
        ):
            """列出任务（支持分页）"""
            try:
                status_filter = TaskStatus(status) if status else None
                type_filter = TaskType(task_type) if task_type else None
                
                # 计算偏移量
                offset = (page - 1) * page_size
                
                tasks = self.task_manager.list_tasks(
                    status=status_filter,
                    task_type=type_filter,
                    limit=page_size,
                    offset=offset,
                    order_by=order_by,
                    order_dir=order_dir
                )
                
                # 获取总数
                total_count = self.task_manager.count_tasks(
                    status=status_filter,
                    task_type=type_filter
                )
                
                return TaskResponse(
                    success=True,
                    data={
                        "tasks": tasks,
                        "pagination": {
                            "page": page,
                            "page_size": page_size,
                            "total": total_count,
                            "total_pages": (total_count + page_size - 1) // page_size
                        }
                    }
                )
            
            except Exception as e:
                self.logger.error(f"列出任务失败: {str(e)}", exc_info=True)
                return TaskResponse(
                    success=False,
                    message=f"列出任务失败: {str(e)}"
                )
        
        @self.app.post("/api/tasks/{task_id}/retry", response_model=TaskResponse)
        async def retry_task(task_id: str):
            """重试失败的任务"""
            try:
                success = self.task_manager.retry_task(task_id)
                
                if success:
                    # 重新执行工作流
                    task_info = self.task_manager.get_task_info(task_id)
                    document_path = task_info.get("document_path")
                    
                    if document_path:
                        asyncio.create_task(
                            self._execute_workflow_async(task_id, document_path, {})
                        )
                    
                    return TaskResponse(
                        success=True,
                        message="任务重试已启动"
                    )
                else:
                    return TaskResponse(
                        success=False,
                        message="任务重试失败"
                    )
            
            except Exception as e:
                self.logger.error(f"重试任务失败: {str(e)}", exc_info=True)
                return TaskResponse(
                    success=False,
                    message=f"重试任务失败: {str(e)}"
                )
        
        @self.app.post("/api/tasks/{task_id}/cancel", response_model=TaskResponse)
        async def cancel_task(task_id: str, reason: Optional[str] = None):
            """取消任务"""
            try:
                success = self.task_manager.cancel_task(task_id, reason)
                
                return TaskResponse(
                    success=success,
                    message="任务已取消" if success else "取消任务失败"
                )
            
            except Exception as e:
                self.logger.error(f"取消任务失败: {str(e)}", exc_info=True)
                return TaskResponse(
                    success=False,
                    message=f"取消任务失败: {str(e)}"
                )
        
        @self.app.delete("/api/tasks/{task_id}", response_model=TaskResponse)
        async def delete_task(task_id: str):
            """删除任务"""
            try:
                # 检查任务是否存在
                task_info = self.task_manager.get_task_info(task_id)
                if not task_info:
                    raise HTTPException(status_code=404, detail="任务不存在")
                
                # 调用TaskManager的删除方法
                success = self.task_manager.delete_task(task_id)
                
                return TaskResponse(
                    success=success,
                    message="任务已删除" if success else "删除任务失败"
                )
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"删除任务失败: {str(e)}", exc_info=True)
                return TaskResponse(
                    success=False,
                    message=f"删除任务失败: {str(e)}"
                )
        
        @self.app.get("/api/statistics", response_model=TaskResponse)
        async def get_statistics():
            """获取统计信息"""
            try:
                stats = self.task_manager.get_task_statistics()
                
                return TaskResponse(
                    success=True,
                    data=stats
                )
            
            except Exception as e:
                self.logger.error(f"获取统计失败: {str(e)}", exc_info=True)
                return TaskResponse(
                    success=False,
                    message=f"获取统计失败: {str(e)}"
                )
        
        @self.app.post("/api/upload", response_model=TaskResponse)
        async def upload_file(file: UploadFile = File(...)):
            """上传文档文件"""
            try:
                # 验证文件类型
                allowed_extensions = [".json", ".yaml", ".yml", ".doc", ".docx"]
                file_ext = Path(file.filename).suffix.lower()
                
                if file_ext not in allowed_extensions:
                    return TaskResponse(
                        success=False,
                        message=f"不支持的文件格式: {file_ext}。支持的格式: {', '.join(allowed_extensions)}"
                    )
                
                # 生成任务ID（用于文件存储）
                import uuid
                task_id = str(uuid.uuid4())
                
                # 创建任务目录
                task_upload_dir = Path("storage/tasks") / task_id / "uploads"
                task_upload_dir.mkdir(parents=True, exist_ok=True)
                
                # 保存文件到任务目录
                file_path = task_upload_dir / file.filename
                
                # 读取并写入文件
                content = await file.read()
                with open(file_path, "wb") as f:
                    f.write(content)
                
                # 计算文件大小
                file_size_kb = round(len(content) / 1024, 2)
                
                # 根据用户偏好添加详细日志
                file_type = "Word文档" if file_ext in [".doc", ".docx"] else "API文档"
                self.logger.info(
                    f"{file_type}上传成功 | 文件: {file.filename} | 大小: {file_size_kb}KB | 路径: {file_path}",
                    file=str(file_path),
                    size_kb=file_size_kb,
                    file_type=file_type,
                    task_id=task_id
                )
                
                return TaskResponse(
                    success=True,
                    message=f"{file_type}上传成功",
                    data={
                        "file_path": str(file_path),
                        "file_name": file.filename,
                        "file_size_kb": file_size_kb,
                        "file_type": file_ext,
                        "task_id": task_id  # 返回任务ID给前端
                    }
                )
            
            except Exception as e:
                self.logger.error(f"文件上传失败: {str(e)}", exc_info=True)
                return TaskResponse(
                    success=False,
                    message=f"文件上传失败: {str(e)}"
                )
        
        @self.app.get("/api/reports/{task_id}/raw", response_model=TaskResponse)
        async def get_raw_report(task_id: str):
            """获取原生 JSON 报告数据"""
            try:
                self.logger.info(
                    f"[获取原生报告] 收到请求 | task_id: {task_id}",
                    task_id=task_id
                )
                
                # 查找最新的 JSON 报告
                task_dir = self.task_manager.storage.get_task_directory(task_id)
                if not task_dir:
                    return TaskResponse(
                        success=False,
                        message="任务不存在"
                    )
                
                from pathlib import Path
                import json
                
                reports_dir = Path(task_dir) / "reports"
                if not reports_dir.exists():
                    return TaskResponse(
                        success=False,
                        message="报告目录不存在"
                    )
                
                # 查找所有 JSON 报告
                report_files = list(reports_dir.glob("test_report_*.json"))
                if not report_files:
                    return TaskResponse(
                        success=False,
                        message="未找到测试报告"
                    )
                
                # 使用最新的报告
                latest_report = max(report_files, key=lambda f: f.stat().st_mtime)
                
                with open(latest_report, 'r', encoding='utf-8') as f:
                    report_data = json.load(f)
                
                self.logger.info(
                    f"[获取原生报告] 成功 | task_id: {task_id} | 文件: {latest_report.name}",
                    task_id=task_id
                )
                
                return TaskResponse(
                    success=True,
                    data=report_data
                )
            
            except Exception as e:
                self.logger.error(f"获取原生报告失败: {str(e)}", exc_info=True)
                return TaskResponse(
                    success=False,
                    message=f"获取报告失败: {str(e)}"
                )
        
        @self.app.get("/api/reports/{task_id}/markdown", response_model=TaskResponse)
        async def get_markdown_report(task_id: str):
            """获取 Markdown 格式报告内容"""
            try:
                self.logger.info(
                    f"[获取Markdown报告] 收到请求 | task_id: {task_id}",
                    task_id=task_id
                )
                
                # 查找最新的 Markdown 报告
                task_dir = self.task_manager.storage.get_task_directory(task_id)
                if not task_dir:
                    return TaskResponse(
                        success=False,
                        message="任务不存在"
                    )
                
                from pathlib import Path
                
                reports_dir = Path(task_dir) / "reports"
                if not reports_dir.exists():
                    return TaskResponse(
                        success=False,
                        message="报告目录不存在"
                    )
                
                # 查找所有 Markdown 报告
                report_files = list(reports_dir.glob("test_report_*.md"))
                if not report_files:
                    return TaskResponse(
                        success=False,
                        message="未找到Markdown报告"
                    )
                
                # 使用最新的报告
                latest_report = max(report_files, key=lambda f: f.stat().st_mtime)
                
                with open(latest_report, 'r', encoding='utf-8') as f:
                    markdown_content = f.read()
                
                self.logger.info(
                    f"[获取Markdown报告] 成功 | task_id: {task_id} | 文件: {latest_report.name}",
                    task_id=task_id
                )
                
                from datetime import datetime
                return TaskResponse(
                    success=True,
                    data={
                        "content": markdown_content,
                        "generated_at": datetime.fromtimestamp(latest_report.stat().st_mtime).isoformat()
                    }
                )
            
            except Exception as e:
                self.logger.error(f"获取Markdown报告失败: {str(e)}", exc_info=True)
                return TaskResponse(
                    success=False,
                    message=f"获取报告失败: {str(e)}"
                )
        
        @self.app.post("/api/reports/{task_id}/analyze", response_model=TaskResponse)
        async def analyze_report(task_id: str):
            """触发 LLM 分析报告"""
            try:
                self.logger.info(
                    f"[分析报告] 收到请求 | task_id: {task_id}",
                    task_id=task_id
                )
                
                # 首先获取原生报告数据
                task_dir = self.task_manager.storage.get_task_directory(task_id)
                if not task_dir:
                    return TaskResponse(
                        success=False,
                        message="任务不存在"
                    )
                
                from pathlib import Path
                import json
                
                reports_dir = Path(task_dir) / "reports"
                if not reports_dir.exists():
                    return TaskResponse(
                        success=False,
                        message="报告目录不存在"
                    )
                
                # 查找最新的 JSON 报告
                report_files = list(reports_dir.glob("test_report_*.json"))
                if not report_files:
                    return TaskResponse(
                        success=False,
                        message="未找到测试报告"
                    )
                
                latest_report = max(report_files, key=lambda f: f.stat().st_mtime)
                
                with open(latest_report, 'r', encoding='utf-8') as f:
                    report_data = json.load(f)
                
                # 调用 ReportAnalyzer
                report_analyzer = self.workflow_orchestrator.mcp_servers.get("report_analyzer")
                if not report_analyzer:
                    return TaskResponse(
                        success=False,
                        message="报告分析服务未注册，请检查配置"
                    )
                
                result = report_analyzer.handle_tool_call("analyze_report", {
                    "task_id": task_id,
                    "report_data": report_data
                })
                
                if result.get("success"):
                    # 可选：将分析结果缓存到文件
                    try:
                        analysis_content = result.get("analysis_markdown", "")
                        if analysis_content:
                            from datetime import datetime
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            analysis_file = reports_dir / f"analysis_report_{timestamp}.md"
                            with open(analysis_file, 'w', encoding='utf-8') as f:
                                f.write(analysis_content)
                            self.logger.info(
                                f"分析报告已缓存 | task_id: {task_id} | 文件: {analysis_file.name}",
                                task_id=task_id
                            )
                    except Exception as e:
                        self.logger.warning(f"缓存分析报告失败: {str(e)}")
                    
                    self.logger.info(
                        f"[分析报告] 成功 | task_id: {task_id}",
                        task_id=task_id
                    )
                    
                    from datetime import datetime
                    return TaskResponse(
                        success=True,
                        data={
                            "content": result.get("analysis_markdown", ""),
                            "generated_at": datetime.now().isoformat()
                        }
                    )
                else:
                    return TaskResponse(
                        success=False,
                        message=result.get("error", "分析失败")
                    )
            
            except Exception as e:
                self.logger.error(f"分析报告失败: {str(e)}", exc_info=True)
                return TaskResponse(
                    success=False,
                    message=f"分析失败: {str(e)}"
                )
        
        @self.app.get("/api/reports/{task_id}")
        async def download_report(task_id: str, format: str = "html"):
            """下载测试报告"""
            try:
                # 获取报告路径
                report_dir = Path(self.config.get("storage_root", "data")) / task_id
                
                if format == "html":
                    report_file = report_dir / "report.html"
                elif format == "markdown":
                    report_file = report_dir / "report.md"
                else:
                    raise HTTPException(status_code=400, detail="不支持的格式")
                
                if not report_file.exists():
                    raise HTTPException(status_code=404, detail="报告不存在")
                
                return FileResponse(
                    path=report_file,
                    filename=f"test_report_{task_id}.{format}",
                    media_type="text/html" if format == "html" else "text/markdown"
                )
            
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"下载报告失败: {str(e)}", exc_info=True)
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket 连接（用于实时推送）"""
            await websocket.accept()
            self.ws_connections.append(websocket)
            
            self.logger.info("WebSocket 连接已建立", ws_count=len(self.ws_connections))
            
            try:
                while True:
                    # 保持连接
                    data = await websocket.receive_text()
                    # 可以处理客户端发送的消息
                    
            except WebSocketDisconnect:
                self.ws_connections.remove(websocket)
                self.logger.info("WebSocket 连接已断开", ws_count=len(self.ws_connections))
    
    async def _execute_workflow_async(
        self,
        task_id: str,
        document_path: str,
        config: Optional[Dict[str, Any]]
    ):
        """异步执行工作流"""
        try:
            success = await self.workflow_orchestrator.execute_workflow(
                task_id,
                document_path,
                config
            )
            
            # 推送完成消息
            await self._broadcast_ws_message({
                "type": "task_completed",
                "task_id": task_id,
                "success": success
            })
        
        except Exception as e:
            self.logger.error(
                f"工作流执行失败 | task_id: {task_id} | 错误: {str(e)}",
                task_id=task_id,
                error=str(e),
                exc_info=True
            )
            
            # 推送错误消息
            await self._broadcast_ws_message({
                "type": "task_error",
                "task_id": task_id,
                "error": str(e)
            })
    
    async def _broadcast_ws_message(self, message: Dict[str, Any]):
        """广播 WebSocket 消息"""
        if not self.ws_connections:
            return
        
        import json
        message_json = json.dumps(message)
        
        for ws in self.ws_connections[:]:  # 复制列表避免迭代时修改
            try:
                await ws.send_text(message_json)
            except Exception as e:
                self.logger.warning(f"WebSocket 发送失败: {str(e)}")
                self.ws_connections.remove(ws)
    
    def run(self, host: str = "0.0.0.0", port: int = 8000, reload: bool = False):
        """
        运行服务
        
        Args:
            host: 服务主机地址
            port: 服务端口
            reload: 是否启用热重载（开发模式）
        """
        import uvicorn
        
        self.logger.info(
            f"启动 Agent HTTP 服务 | {host}:{port} | 热重载: {reload}",
            host=host,
            port=port,
            reload=reload
        )
        
        if reload:
            # 热重载模式：监控文件变化自动重启
            uvicorn.run(
                "backend.main:create_app",  # 使用app工厂函数
                factory=True,  # 告诉uvicorn这是一个app工厂函数
                host=host,
                port=port,
                reload=True,
                log_level="info",
                reload_dirs=["backend"],  # 监控backend目录
                reload_includes=["*.py"]  # 只监控Python文件
            )
        else:
            # 普通模式
            uvicorn.run(self.app, host=host, port=port, log_level="info")
