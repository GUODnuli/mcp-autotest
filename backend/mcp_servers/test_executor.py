"""
自动化测试执行 MCP Server

负责测试用例的执行、引擎选择、并发控制和进度推送。
"""

import json
import asyncio
import time
from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from backend.mcp_servers.base import MCPServer
from backend.common.logger import Logger
from backend.common.database import Database
from backend.common.storage import StorageManager
from backend.common.test_models import (
    TestCase,
    TestResult,
    TestSuite,
    TestCaseStatus,
    TestReport,
    calculate_pass_rate
)
from backend.common.engines import RequestsEngine, HttpRunnerEngine
from backend.common.report_generator import ReportGenerator


class TestExecutor(MCPServer):
    """
    自动化测试执行 MCP Server
    
    功能：
    - 支持多种测试引擎（Requests、HttpRunner）
    - 支持并发执行测试用例
    - 实时进度推送
    - 生成详细的测试报告
    - 支持测试用例依赖管理
    """
    
    def __init__(self, config: Dict[str, Any], logger: Logger, 
                 database: Database, storage: StorageManager):
        super().__init__("test_executor", "1.0.0")
        self.config = config
        self.database = database
        self.storage = storage
        # 覆盖基类的 logger
        self.logger = logger
        
        # 测试引擎池
        self.engines: Dict[str, Any] = {}
        self._init_engines()
        
        # 线程池（用于并发执行）
        max_workers = config.get("max_workers", 5)
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        
        self.logger.info(
            f"TestExecutor 初始化完成 | "
            f"支持引擎: {list(self.engines.keys())} | "
            f"最大并发: {max_workers}",
            server="test_executor"
        )
    
    def _init_engines(self):
        """初始化测试引擎"""
        engine_configs = self.config.get("engines", {})
        
        # 初始化 Requests 引擎
        if engine_configs.get("requests", {}).get("enabled", True):
            requests_config = engine_configs.get("requests", {})
            requests_engine = RequestsEngine()
            requests_engine.initialize(requests_config)
            self.engines["requests"] = requests_engine
            self.logger.info("Requests 引擎已初始化", engine="requests")
        
        # 初始化 HttpRunner 引擎（可选）
        if engine_configs.get("httprunner", {}).get("enabled", False):
            try:
                httprunner_config = engine_configs.get("httprunner", {})
                httprunner_engine = HttpRunnerEngine()
                httprunner_engine.initialize(httprunner_config)
                self.engines["httprunner"] = httprunner_engine
                self.logger.info("HttpRunner 引擎已初始化", engine="httprunner")
            except Exception as e:
                self.logger.warning(
                    f"HttpRunner 引擎初始化失败: {str(e)}",
                    engine="httprunner"
                )
    
    def get_tools(self) -> List[Dict[str, Any]]:
        """返回支持的工具列表"""
        return [
            {
                "name": "execute_testcases",
                "description": "执行一组测试用例",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "任务ID"
                        },
                        "testcases": {
                            "type": "array",
                            "description": "测试用例列表（JSON格式）",
                            "items": {"type": "object"}
                        },
                        "engine": {
                            "type": "string",
                            "description": "指定测试引擎（requests/httprunner/auto），默认 auto",
                            "enum": ["requests", "httprunner", "auto"]
                        },
                        "parallel": {
                            "type": "boolean",
                            "description": "是否并发执行，默认 false"
                        },
                        "fail_fast": {
                            "type": "boolean",
                            "description": "遇到失败立即停止，默认 false"
                        }
                    },
                    "required": ["task_id", "testcases"]
                }
            },
            {
                "name": "execute_testsuite",
                "description": "执行测试套件",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "任务ID"
                        },
                        "testsuite": {
                            "type": "object",
                            "description": "测试套件对象（JSON格式）"
                        },
                        "engine": {
                            "type": "string",
                            "description": "指定测试引擎，默认 auto"
                        },
                        "parallel": {
                            "type": "boolean",
                            "description": "是否并发执行"
                        }
                    },
                    "required": ["task_id", "testsuite"]
                }
            },
            {
                "name": "get_execution_progress",
                "description": "获取测试执行进度",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "任务ID"
                        }
                    },
                    "required": ["task_id"]
                }
            }
        ]
    
    def handle_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具调用"""
        try:
            if tool_name == "execute_testcases":
                return self._execute_testcases(arguments)
            
            elif tool_name == "execute_testsuite":
                return self._execute_testsuite(arguments)
            
            elif tool_name == "get_execution_progress":
                return self._get_execution_progress(arguments)
            
            else:
                return {
                    "success": False,
                    "error": f"未知工具: {tool_name}"
                }
        
        except Exception as e:
            self.logger.error(
                f"工具调用失败 | 工具: {tool_name} | 错误: {str(e)}",
                tool=tool_name,
                error=str(e),
                exc_info=True
            )
            return {
                "success": False,
                "error": f"执行异常: {str(e)}"
            }
    
    def _execute_testcases(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行测试用例列表
        
        Args:
            arguments: 工具参数
            
        Returns:
            执行结果
        """
        task_id = arguments["task_id"]
        testcases_data = arguments["testcases"]
        engine_name = arguments.get("engine", "auto")
        parallel = arguments.get("parallel", False)
        fail_fast = arguments.get("fail_fast", False)
        
        self.logger.info(
            f"开始执行测试用例 | "
            f"任务ID: {task_id} | "
            f"用例数: {len(testcases_data)} | "
            f"引擎: {engine_name} | "
            f"并发: {parallel}",
            task_id=task_id,
            count=len(testcases_data)
        )
        
        # 解析测试用例
        testcases = []
        for tc_data in testcases_data:
            try:
                testcase = TestCase(**tc_data)
                testcases.append(testcase)
            except Exception as e:
                # 避免 loguru 格式化冲突，使用字符串拼接
                try:
                    import json
                    tc_data_str = json.dumps(tc_data, ensure_ascii=False)
                    log_msg = "测试用例解析失败: " + str(e) + " | 数据: " + tc_data_str
                    from loguru import logger
                    logger.opt(raw=True).warning(log_msg + "\n")
                except:
                    self.logger.warning(
                        f"测试用例解析失败: {str(e)}",
                        task_id=task_id
                    )
        
        if not testcases:
            return {
                "success": False,
                "error": "没有有效的测试用例"
            }
        
        # 选择测试引擎
        engine = self._select_engine(engine_name)
        if not engine:
            return {
                "success": False,
                "error": f"测试引擎不可用: {engine_name}"
            }
        
        # 执行测试
        start_time = time.time()
        
        if parallel:
            results = self._execute_parallel(testcases, engine, fail_fast, task_id)
        else:
            results = self._execute_sequential(testcases, engine, fail_fast, task_id)
        
        duration = time.time() - start_time
        
        # 生成测试报告
        report = self._generate_report(task_id, results, duration)
        
        # 保存 JSON 报告
        report_path = self.storage.save_test_report(task_id, report.model_dump())
        
        # 生成并保存 Markdown 报告
        try:
            report_generator = ReportGenerator(logger=self.logger)
            markdown_content = report_generator.generate_markdown(report)
            md_report_path = self.storage.save_report(
                task_id=task_id,
                report_content=markdown_content,
                report_format="md"
            )
            self.logger.info(
                f"Markdown 报告已生成 | task_id: {task_id} | 路径: {md_report_path}",
                task_id=task_id
            )
        except Exception as e:
            self.logger.warning(
                f"Markdown 报告生成失败 | task_id: {task_id} | 错误: {str(e)}",
                task_id=task_id
            )
        
        self.logger.info(
            f"测试执行完成 | "
            f"任务ID: {task_id} | "
            f"总数: {report.total_count} | "
            f"通过: {report.passed_count} | "
            f"失败: {report.failed_count} | "
            f"通过率: {report.pass_rate}% | "
            f"耗时: {duration:.2f}s",
            task_id=task_id,
            report=report.model_dump()
        )
        
        return {
            "success": True,
            "report": report.model_dump(),
            "report_path": str(report_path)
        }
    
    def _execute_testsuite(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行测试套件
        
        Args:
            arguments: 工具参数
            
        Returns:
            执行结果
        """
        task_id = arguments["task_id"]
        testsuite_data = arguments["testsuite"]
        engine_name = arguments.get("engine", "auto")
        parallel = arguments.get("parallel", False)
        
        try:
            testsuite = TestSuite(**testsuite_data)
        except Exception as e:
            return {
                "success": False,
                "error": f"测试套件解析失败: {str(e)}"
            }
        
        self.logger.info(
            f"开始执行测试套件 | "
            f"任务ID: {task_id} | "
            f"套件: {testsuite.name} | "
            f"用例数: {len(testsuite.testcases)}",
            task_id=task_id,
            suite_name=testsuite.name
        )
        
        # 委托给 execute_testcases
        return self._execute_testcases({
            "task_id": task_id,
            "testcases": [tc.model_dump() for tc in testsuite.testcases],
            "engine": engine_name,
            "parallel": parallel
        })
    
    def _execute_sequential(
        self,
        testcases: List[TestCase],
        engine: Any,
        fail_fast: bool,
        task_id: str
    ) -> List[TestResult]:
        """
        顺序执行测试用例
        
        Args:
            testcases: 测试用例列表
            engine: 测试引擎
            fail_fast: 是否快速失败
            task_id: 任务ID
            
        Returns:
            测试结果列表
        """
        results = []
        
        for i, testcase in enumerate(testcases, 1):
            self.logger.debug(
                f"执行测试用例 {i}/{len(testcases)} | ID: {testcase.id}",
                task_id=task_id,
                progress=f"{i}/{len(testcases)}"
            )
            
            result = engine.execute_testcase(testcase)
            results.append(result)
            
            # 更新进度
            self._update_progress(task_id, i, len(testcases), result)
            
            # 快速失败检查
            if fail_fast and result.status in [TestCaseStatus.FAILED, TestCaseStatus.ERROR]:
                self.logger.warning(
                    f"检测到失败，停止执行 | 任务ID: {task_id}",
                    task_id=task_id
                )
                break
        
        return results
    
    def _execute_parallel(
        self,
        testcases: List[TestCase],
        engine: Any,
        fail_fast: bool,
        task_id: str
    ) -> List[TestResult]:
        """
        并发执行测试用例
        
        Args:
            testcases: 测试用例列表
            engine: 测试引擎
            fail_fast: 是否快速失败
            task_id: 任务ID
            
        Returns:
            测试结果列表
        """
        results = []
        completed_count = 0
        should_stop = False
        
        # 提交所有任务
        futures = {
            self.executor.submit(engine.execute_testcase, tc): tc
            for tc in testcases
        }
        
        # 等待完成
        for future in as_completed(futures):
            if should_stop:
                future.cancel()
                continue
            
            testcase = futures[future]
            
            try:
                result = future.result()
                results.append(result)
                completed_count += 1
                
                self.logger.debug(
                    f"测试用例完成 | ID: {testcase.id} | "
                    f"进度: {completed_count}/{len(testcases)}",
                    task_id=task_id,
                    testcase_id=testcase.id
                )
                
                # 更新进度
                self._update_progress(task_id, completed_count, len(testcases), result)
                
                # 快速失败检查
                if fail_fast and result.status in [TestCaseStatus.FAILED, TestCaseStatus.ERROR]:
                    self.logger.warning(
                        f"检测到失败，停止并发执行 | 任务ID: {task_id}",
                        task_id=task_id
                    )
                    should_stop = True
            
            except Exception as e:
                self.logger.error(
                    f"测试用例执行异常 | ID: {testcase.id} | 错误: {str(e)}",
                    task_id=task_id,
                    testcase_id=testcase.id,
                    error=str(e)
                )
        
        return results
    
    def _select_engine(self, engine_name: str) -> Optional[Any]:
        """
        选择测试引擎
        
        Args:
            engine_name: 引擎名称（requests/httprunner/auto）
            
        Returns:
            测试引擎实例
        """
        if engine_name == "auto":
            # 自动选择：优先 Requests
            if "requests" in self.engines:
                return self.engines["requests"]
            elif "httprunner" in self.engines:
                return self.engines["httprunner"]
            else:
                return None
        
        return self.engines.get(engine_name)
    
    def _update_progress(
        self,
        task_id: str,
        current: int,
        total: int,
        latest_result: TestResult
    ):
        """
        更新执行进度
        
        Args:
            task_id: 任务ID
            current: 当前完成数
            total: 总数
            latest_result: 最新结果
        """
        progress = {
            "current": current,
            "total": total,
            "percentage": round((current / total) * 100, 2),
            "latest_result": {
                "testcase_id": latest_result.testcase_id,
                "status": latest_result.status,
                "duration": latest_result.duration
            }
        }
        
        # 保存到检查点（用于断点续传）
        try:
            self.database.save_checkpoint(
                task_id,
                {"execution_progress": progress}
            )
        except Exception as e:
            self.logger.warning(
                f"保存进度失败 | 任务ID: {task_id} | 错误: {str(e)}",
                task_id=task_id
            )
    
    def _get_execution_progress(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取测试执行进度
        
        Args:
            arguments: 工具参数
            
        Returns:
            进度信息
        """
        task_id = arguments["task_id"]
        
        try:
            checkpoint = self.database.get_checkpoint(task_id)
            if checkpoint and "execution_progress" in checkpoint:
                return {
                    "success": True,
                    "progress": checkpoint["execution_progress"]
                }
            else:
                return {
                    "success": True,
                    "progress": None,
                    "message": "暂无进度信息"
                }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"获取进度失败: {str(e)}"
            }
    
    def _generate_report(
        self,
        task_id: str,
        results: List[TestResult],
        duration: float
    ) -> TestReport:
        """
        生成测试报告
        
        Args:
            task_id: 任务ID
            results: 测试结果列表
            duration: 总耗时
            
        Returns:
            测试报告对象
        """
        # 统计数据
        total_count = len(results)
        passed_count = sum(1 for r in results if r.status == TestCaseStatus.PASSED)
        failed_count = sum(1 for r in results if r.status == TestCaseStatus.FAILED)
        error_count = sum(1 for r in results if r.status == TestCaseStatus.ERROR)
        skipped_count = sum(1 for r in results if r.status == TestCaseStatus.SKIPPED)
        
        pass_rate = calculate_pass_rate(passed_count, total_count)
        
        # 最慢用例 Top 10
        slowest = sorted(results, key=lambda r: r.duration, reverse=True)[:10]
        slowest_testcases = [
            {
                "testcase_id": r.testcase_id,
                "interface_name": r.interface_name,
                "duration": r.duration
            }
            for r in slowest
        ]
        
        # 错误模式分析（简单版本：按错误信息分组）
        error_patterns = {}
        for r in results:
            if r.error_message:
                key = r.error_message[:100]  # 取前100字符作为键
                if key not in error_patterns:
                    error_patterns[key] = {"count": 0, "example_id": r.testcase_id}
                error_patterns[key]["count"] += 1
        
        error_patterns_list = [
            {"pattern": k, "count": v["count"], "example_id": v["example_id"]}
            for k, v in sorted(error_patterns.items(), key=lambda x: x[1]["count"], reverse=True)
        ]
        
        # 创建报告对象
        report = TestReport(
            task_id=task_id,
            total_count=total_count,
            passed_count=passed_count,
            failed_count=failed_count,
            error_count=error_count,
            skipped_count=skipped_count,
            pass_rate=pass_rate,
            total_duration=duration,
            testcase_results=results,
            slowest_testcases=slowest_testcases,
            error_patterns=error_patterns_list
        )
        
        return report
    
    def cleanup(self):
        """清理资源"""
        # 清理测试引擎
        for engine_name, engine in self.engines.items():
            try:
                engine.cleanup()
                self.logger.debug(f"引擎已清理: {engine_name}")
            except Exception as e:
                self.logger.warning(f"引擎清理失败: {engine_name} | 错误: {str(e)}")
        
        # 关闭线程池
        self.executor.shutdown(wait=True)
        
        self.logger.info("TestExecutor 资源已清理", server="test_executor")
