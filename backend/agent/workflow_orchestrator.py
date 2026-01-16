"""
工作流编排器

负责 MCP Server 调度、依赖分析和错误回滚。
"""

import json
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

from backend.agent.task_manager import TaskManager, TaskState
from backend.common.logger import Logger
from backend.common.database import Database, TaskType
from backend.common.storage import StorageManager
from backend.common.memory import MemoryManager


class WorkflowStep(str, Enum):
    """工作流步骤"""
    PARSE_DOCUMENT = "parse_document"
    GENERATE_TESTCASES = "generate_testcases"
    EXECUTE_TESTS = "execute_tests"
    GENERATE_REPORT = "generate_report"


class WorkflowOrchestrator:
    """
    工作流编排器
    
    功能：
    - MCP Server 调度和协调
    - 工作流步骤依赖分析
    - 错误处理和回滚
    - 数据流管理（步骤间数据传递）
    
    工作流：
    1. 解析文档 → 2. 生成测试用例 → 3. 执行测试 → 4. 生成报告
    """
    
    def __init__(
        self,
        task_manager: TaskManager,
        logger: Logger,
        database: Database,
        storage: StorageManager,
        memory_manager: MemoryManager
    ):
        self.task_manager = task_manager
        self.logger = logger
        self.database = database
        self.storage = storage
        self.memory_manager = memory_manager
        
        # MCP Server 代理（将在初始化时注入）
        self.mcp_servers: Dict[str, Any] = {}
        
        # 工作流定义（步骤依赖关系）
        self.workflow_definition = {
            WorkflowStep.PARSE_DOCUMENT: {
                "depends_on": [],
                "state": TaskState.PARSING_DOC,
                "next_step": WorkflowStep.GENERATE_TESTCASES
            },
            WorkflowStep.GENERATE_TESTCASES: {
                "depends_on": [WorkflowStep.PARSE_DOCUMENT],
                "state": TaskState.GENERATING_TESTCASES,
                "next_step": WorkflowStep.EXECUTE_TESTS
            },
            WorkflowStep.EXECUTE_TESTS: {
                "depends_on": [WorkflowStep.GENERATE_TESTCASES],
                "state": TaskState.EXECUTING_TESTS,
                "next_step": WorkflowStep.GENERATE_REPORT
            },
            WorkflowStep.GENERATE_REPORT: {
                "depends_on": [WorkflowStep.EXECUTE_TESTS],
                "state": TaskState.GENERATING_REPORT,
                "next_step": None  # 最后一步
            }
        }
        
        self.logger.info(
            "WorkflowOrchestrator 初始化完成 | "
            f"工作流步骤: {[s.value for s in WorkflowStep]}",
            component="WorkflowOrchestrator"
        )
    
    def register_mcp_server(self, name: str, server: Any):
        """
        注册 MCP Server
        
        Args:
            name: Server 名称
            server: Server 实例
        """
        self.mcp_servers[name] = server
        self.logger.info(f"MCP Server 已注册: {name}", server=name)
    
    async def execute_workflow(
        self,
        task_id: str,
        document_path: str,
        config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        执行完整工作流
        
        Args:
            task_id: 任务ID
            document_path: 文档路径
            config: 配置参数
            
        Returns:
            执行是否成功
        """
        self.logger.info(
            f"开始执行工作流 | task_id: {task_id} | 文档: {document_path}",
            task_id=task_id,
            document_path=document_path
        )
        
        config = config or {}
        workflow_context = {
            "document_path": document_path,
            "config": config
        }
        
        try:
            # 步骤 1: 解析文档
            success = await self._execute_step(
                task_id,
                WorkflowStep.PARSE_DOCUMENT,
                workflow_context
            )
            if not success:
                return False
            
            # 步骤 2: 生成测试用例
            success = await self._execute_step(
                task_id,
                WorkflowStep.GENERATE_TESTCASES,
                workflow_context
            )
            if not success:
                return False
            
            # 步骤 3: 执行测试
            success = await self._execute_step(
                task_id,
                WorkflowStep.EXECUTE_TESTS,
                workflow_context
            )
            if not success:
                return False
            
            # 步骤 4: 生成报告
            success = await self._execute_step(
                task_id,
                WorkflowStep.GENERATE_REPORT,
                workflow_context
            )
            if not success:
                return False
            
            # 标记完成
            success = self.task_manager.transition_state(
                task_id,
                TaskState.COMPLETED,
                {"completed_context": workflow_context}
            )
            
            # 如果状态转换失败（例如状态不存在），强制设置为完成
            if not success:
                self.logger.warning(
                    f"状态转换失败，强制标记为完成 | task_id: {task_id}",
                    task_id=task_id
                )
                # 直接保存检查点和数据库状态
                self.task_manager._save_checkpoint(
                    task_id,
                    TaskState.COMPLETED,
                    {"completed_context": workflow_context}
                )
                self.task_manager._update_database_status(task_id, TaskState.COMPLETED)
            
            self.logger.info(
                f"工作流执行成功 | task_id: {task_id}",
                task_id=task_id
            )
            
            return True
        
        except Exception as e:
            self.logger.error(
                f"工作流执行失败 | task_id: {task_id} | 错误: {str(e)}",
                task_id=task_id,
                error=str(e),
                exc_info=True
            )
            
            # 标记失败
            current_state = self.task_manager.get_task_state(task_id)
            self.task_manager.mark_task_failed(
                task_id,
                str(e),
                failed_at_state=current_state
            )
            
            return False
    
    async def _execute_step(
        self,
        task_id: str,
        step: WorkflowStep,
        context: Dict[str, Any]
    ) -> bool:
        """
        执行单个工作流步骤
        
        Args:
            task_id: 任务ID
            step: 工作流步骤
            context: 工作流上下文
            
        Returns:
            执行是否成功
        """
        step_def = self.workflow_definition[step]
        
        # 转换状态
        self.task_manager.transition_state(
            task_id,
            step_def["state"],
            {"step": step.value}
        )
        
        self.logger.info(
            f"执行工作流步骤 | task_id: {task_id} | 步骤: {step.value}",
            task_id=task_id,
            step=step.value
        )
        
        try:
            # 根据步骤调用相应的处理器
            if step == WorkflowStep.PARSE_DOCUMENT:
                result = await self._parse_document(task_id, context)
            elif step == WorkflowStep.GENERATE_TESTCASES:
                result = await self._generate_testcases(task_id, context)
            elif step == WorkflowStep.EXECUTE_TESTS:
                result = await self._execute_tests(task_id, context)
            elif step == WorkflowStep.GENERATE_REPORT:
                result = await self._generate_report(task_id, context)
            else:
                raise ValueError(f"未知步骤: {step}")
            
            if not result["success"]:
                raise Exception(result.get("error", "步骤执行失败"))
            
            # 更新上下文
            context[step.value] = result
            
            self.logger.info(
                f"工作流步骤完成 | task_id: {task_id} | 步骤: {step.value}",
                task_id=task_id,
                step=step.value
            )
            
            return True
        
        except Exception as e:
            self.logger.error(
                f"工作流步骤失败 | task_id: {task_id} | 步骤: {step.value} | 错误: {str(e)}",
                task_id=task_id,
                step=step.value,
                error=str(e)
            )
            raise
    
    async def _parse_document(
        self,
        task_id: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """解析文档步骤"""
        document_path = context["document_path"]
        
        # 调用文档解析 MCP Server
        doc_parser = self.mcp_servers.get("doc_parser")
        if not doc_parser:
            return {"success": False, "error": "文档解析 Server 未注册"}
        
        result = doc_parser.handle_tool_call("parse_document", {
            "task_id": task_id,  # 传递task_id给解析器
            "document_path": document_path,
            "parse_strategy": "auto"
        })
        
        if result.get("success"):
            # 保存解析结果
            interfaces = result.get("interfaces", [])
            self.storage.save_interfaces(task_id, interfaces)
            
            # 存入记忆（用于后续上下文增强）
            if interfaces:  # 只有当有接口时才存储
                for interface in interfaces:
                    interface_name = interface.get("name", "unknown")
                    self.memory_manager.memorize_interface(
                        interface_name=interface_name,
                        interface_data=interface,
                        task_id=task_id
                    )
            
            self.logger.info(
                f"文档解析成功 | task_id: {task_id} | 接口数: {len(interfaces)}",
                task_id=task_id,
                interface_count=len(interfaces)
            )
        
        return result
    
    async def _generate_testcases(
        self,
        task_id: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """生成测试用例步骤"""
        # 检查是否为Word文档
        parse_result = context.get("parse_document", {})
        # parse_result 就是直接的结果，不需要再取 result 字段
        is_word_document = parse_result.get("is_word_document", False)
        llm_processed = parse_result.get("llm_processed", False)
        
        if is_word_document:
            if llm_processed:
                self.logger.info(
                    f"Word文档已通过 LLM 处理，继续正常流程 | task_id: {task_id}",
                    task_id=task_id
                )
            else:
                # Word文档未通过 LLM 处理，提示错误
                self.logger.warning(
                    f"Word文档未通过 LLM 处理 | task_id: {task_id}",
                    task_id=task_id
                )
                return {
                    "success": False,
                    "error": "Word文档解析成功，但未配置 LLM 客户端。请配置 config/dify.toml 后重试。"
                }
        
        # 标准流程：从接口列表生成测试用例
        # 加载解析的接口
        interfaces = self.storage.load_interfaces(task_id) 
        if not interfaces:
            return {"success": False, "error": "未找到解析的接口数据"}
        
        # 调用测试用例生成 MCP Server
        testcase_generator = self.mcp_servers.get("testcase_generator")
        if not testcase_generator:
            return {"success": False, "error": "测试用例生成 Server 未注册"}
        
        all_testcases = []
        
        for interface in interfaces:
            interface_name = interface.get("name", "unknown")
            
            self.logger.info(
                f"开始生成测试用例 | task_id: {task_id} | 接口: {interface_name}",
                task_id=task_id,
                interface=interface_name
            )
            
            # 打印接口规范
            import json
            self.logger.debug(
                f"接口规范 | {json.dumps(interface, ensure_ascii=False, indent=2)}",
                task_id=task_id
            )
            
            result = testcase_generator.handle_tool_call("generate_testcases", {
                "task_id": task_id,
                "interface": interface  # 注意参数名是 interface 不是 interface_spec
            })
            
            # 打印生成结果
            self.logger.info(
                f"generate_testcase 返回 | task_id: {task_id} | "
                f"success: {result.get('success')} | "
                f"用例数: {result.get('testcase_count', 0)}",
                task_id=task_id
            )
            
            if not result.get("success"):
                self.logger.error(
                    f"测试用例生成失败 | task_id: {task_id} | "
                    f"接口: {interface_name} | 错误: {result.get('error')}",
                    task_id=task_id
                )
                continue
            
            if result.get("success"):
                testcases = result.get("testcases", [])
                
                # 打印测试用例内容（避免 f-string 格式化冲突）
                if testcases:
                    try:
                        testcases_json = json.dumps(testcases, ensure_ascii=False, indent=2)
                        log_msg = "\u751f\u6210\u7684\u6d4b\u8bd5\u7528\u4f8b | task_id: " + str(task_id) + " | \u63a5\u53e3: " + interface_name + " | \u7528\u4f8b\u5185\u5bb9:\n" + testcases_json
                        from loguru import logger
                        logger.opt(raw=True).info(log_msg + "\n")
                    except Exception as e:
                        self.logger.warning(
                            f"\u6d4b\u8bd5\u7528\u4f8b\u65e5\u5fd7\u6253\u5370\u5931\u8d25: {str(e)}",
                            task_id=task_id
                        )
                else:
                    self.logger.warning(
                        f"未生成任何测试用例 | task_id: {task_id} | 接口: {interface_name}",
                        task_id=task_id
                    )
                
                all_testcases.extend(testcases)
                
                # 按接口单独保存测试用例
                if testcases:
                    self.storage.save_testcases(task_id, interface_name, testcases)
                    self.logger.info(
                        f"接口测试用例保存成功 | task_id: {task_id} | "
                        f"接口: {interface_name} | 用例数: {len(testcases)}",
                        task_id=task_id
                    )
        
        self.logger.info(
            f"测试用例生成成功 | task_id: {task_id} | 用例数: {len(all_testcases)}",
            task_id=task_id,
            testcase_count=len(all_testcases)
        )
        
        return {
            "success": True,
            "testcase_count": len(all_testcases)
        }
    
    async def _execute_tests(
        self,
        task_id: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行测试步骤"""
        # 加载所有测试用例
        testcases = self.storage.load_all_testcases(task_id)
        if not testcases:
            return {"success": False, "error": "未找到测试用例"}
        
        # 调用测试执行 MCP Server
        test_executor = self.mcp_servers.get("test_executor")
        if not test_executor:
            return {"success": False, "error": "测试执行 Server 未注册"}
        
        config = context.get("config", {})
        result = test_executor.handle_tool_call("execute_testcases", {
            "task_id": task_id,
            "testcases": testcases,
            "engine": config.get("test_engine", "auto"),
            "parallel": config.get("parallel_execution", False),
            "fail_fast": config.get("fail_fast", False)
        })
        
        if result.get("success"):
            self.logger.info(
                f"测试执行成功 | task_id: {task_id}",
                task_id=task_id
            )
        
        return result
    
    async def _generate_report(
        self,
        task_id: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """生成报告步骤（报告已在 execute_tests 中生成）"""
        # 报告已在测试执行步骤中生成，这里直接返回成功
        self.logger.info(
            f"报告已生成 | task_id: {task_id}",
            task_id=task_id
        )
        
        return {
            "success": True,
            "message": "测试报告已在测试执行中生成"
        }
    
    def rollback_step(
        self,
        task_id: str,
        step: WorkflowStep
    ) -> bool:
        """
        回滚工作流步骤
        
        Args:
            task_id: 任务ID
            step: 要回滚的步骤
            
        Returns:
            回滚是否成功
        """
        self.logger.warning(
            f"回滚工作流步骤 | task_id: {task_id} | 步骤: {step.value}",
            task_id=task_id,
            step=step.value
        )
        
        try:
            # 清理步骤产生的数据
            if step == WorkflowStep.PARSE_DOCUMENT:
                # 清理解析的接口数据
                pass
            elif step == WorkflowStep.GENERATE_TESTCASES:
                # 清理生成的测试用例
                pass
            elif step == WorkflowStep.EXECUTE_TESTS:
                # 清理测试结果
                pass
            
            # 回退状态
            step_def = self.workflow_definition[step]
            depends_on = step_def["depends_on"]
            
            if depends_on:
                # 回退到前一个步骤的状态
                prev_step = depends_on[-1]
                prev_state = self.workflow_definition[prev_step]["state"]
                self.task_manager.transition_state(
                    task_id,
                    prev_state,
                    {"rollback_from": step.value}
                )
            else:
                # 回退到初始状态
                self.task_manager.transition_state(
                    task_id,
                    TaskState.CREATED,
                    {"rollback_from": step.value}
                )
            
            return True
        
        except Exception as e:
            self.logger.error(
                f"回滚失败 | task_id: {task_id} | 步骤: {step.value} | 错误: {str(e)}",
                task_id=task_id,
                step=step.value,
                error=str(e)
            )
            return False
