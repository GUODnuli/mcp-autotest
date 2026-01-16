"""
测试用例生成 MCP Server

基于 Dify 工作流 API 生成测试用例，支持多种测试策略。
"""

import json
from typing import Any, Dict, List, Optional

from backend.mcp_servers.base import MCPServer, MCPError
from backend.common.logger import Logger
from backend.common.database import Database
from backend.common.storage import StorageManager
from backend.common.memory import MemoryManager
from backend.common.dify_client import DifyClient, DifyAPIError
from backend.common.test_models import (
    TestCase,
    Request,
    Assertion,
    AssertionType,
    AssertionOperator
)


class TestCaseGenerator(MCPServer):
    """
    测试用例生成 MCP Server
    
    功能：
    - 调用 Dify 工作流 API 生成测试用例
    - 支持多种测试策略（正向、边界、异常等）
    - 利用记忆管理器进行上下文增强
    - 批量生成测试用例
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        logger: Logger,
        database: Database,
        storage: StorageManager,
        memory_manager: Optional[MemoryManager] = None
    ):
        super().__init__("testcase_generator", "1.0.0")
        self.config = config
        self.database = database
        self.storage = storage
        self.memory_manager = memory_manager
        # 覆盖基类的 logger
        self.logger = logger
        
        # 初始化 Dify 客户端
        self.dify_client = DifyClient(config)
        
        # 测试策略定义
        self.test_strategies = {
            "positive": "正向测试：验证正常输入下接口的正确行为",
            "negative": "负向测试：验证非法输入下接口的错误处理",
            "boundary": "边界测试：验证边界值和极限情况",
            "security": "安全测试：验证常见安全漏洞防护",
            "performance": "性能测试：验证接口响应时间和吞吐量"
        }
        
        self.logger.info(
            "TestCaseGenerator 初始化完成",
            server="testcase_generator"
        )
    
    def get_tools(self) -> List[Dict[str, Any]]:
        """返回支持的工具列表"""
        return [
            {
                "name": "generate_testcases",
                "description": "为接口生成测试用例",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "任务ID"
                        },
                        "interface": {
                            "type": "object",
                            "description": "接口信息（来自 doc_parser）"
                        },
                        "strategies": {
                            "type": "array",
                            "description": "测试策略列表",
                            "items": {
                                "type": "string",
                                "enum": ["positive", "negative", "boundary", "security", "performance"]
                            }
                        },
                        "count_per_strategy": {
                            "type": "integer",
                            "description": "每种策略生成的用例数量，默认 3"
                        },
                        "use_context_enhancement": {
                            "type": "boolean",
                            "description": "是否使用上下文增强（利用记忆管理器），默认 true"
                        }
                    },
                    "required": ["task_id", "interface"]
                }
            },
            {
                "name": "generate_batch_testcases",
                "description": "批量为多个接口生成测试用例",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "任务ID"
                        },
                        "interfaces": {
                            "type": "array",
                            "description": "接口信息列表",
                            "items": {"type": "object"}
                        },
                        "strategies": {
                            "type": "array",
                            "description": "测试策略列表"
                        },
                        "count_per_strategy": {
                            "type": "integer",
                            "description": "每种策略生成的用例数量"
                        }
                    },
                    "required": ["task_id", "interfaces"]
                }
            },
            {
                "name": "get_test_strategies",
                "description": "获取支持的测试策略列表",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "get_generated_testcases",
                "description": "获取已生成的测试用例",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "任务ID"
                        },
                        "interface_name": {
                            "type": "string",
                            "description": "接口名称（可选，不指定则返回所有）"
                        }
                    },
                    "required": ["task_id"]
                }
            }
        ]
    
    def handle_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具调用"""
        try:
            if tool_name == "generate_testcases":
                return self._generate_testcases(arguments)
            
            elif tool_name == "generate_batch_testcases":
                return self._generate_batch_testcases(arguments)
            
            elif tool_name == "get_test_strategies":
                return self._get_test_strategies()
            
            elif tool_name == "get_generated_testcases":
                return self._get_generated_testcases(arguments)
            
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
    
    def _generate_testcases(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        为单个接口生成测试用例
        
        Args:
            arguments: 工具参数
            
        Returns:
            生成结果
        """
        task_id = arguments["task_id"]
        interface = arguments["interface"]
        strategies = arguments.get("strategies", ["positive", "negative"])
        count_per_strategy = arguments.get("count_per_strategy", 3)
        use_context_enhancement = arguments.get("use_context_enhancement", True)
        
        interface_name = interface.get("name", "unknown")
        
        self.logger.info(
            f"开始生成测试用例 | "
            f"任务ID: {task_id} | "
            f"接口: {interface_name} | "
            f"策略: {strategies}",
            task_id=task_id,
            interface=interface_name
        )
        
        # 构建上下文增强信息
        enhanced_context = ""
        if use_context_enhancement and self.memory_manager:
            try:
                interface_desc = f"{interface.get('method', '')} {interface.get('path', '')} - {interface.get('description', '')}"
                enhanced_context = self.memory_manager.build_enhanced_context(
                    interface_desc,
                    max_context_items=3
                )
            except Exception as e:
                self.logger.warning(
                    f"上下文增强失败: {str(e)}",
                    task_id=task_id
                )
        
        # 构建 Dify 工作流输入
        workflow_input = self._build_workflow_input(
            interface=interface,
            strategies=strategies,
            count_per_strategy=count_per_strategy,
            enhanced_context=enhanced_context
        )
        
        # 调用 Dify API
        try:
            dify_output = self.dify_client.call_workflow(
                inputs=workflow_input,
                user=f"task_{task_id}"
            )
            
            # 先打印基本信息
            self.logger.info(
                f"Dify API 响应类型 | task_id: {task_id} | 类型: {type(dify_output).__name__}",
                task_id=task_id
            )
            
            # 如果是字典，打印键列表
            if isinstance(dify_output, dict):
                self.logger.info(
                    f"Dify API 响应键 | task_id: {task_id} | 键列表: {list(dify_output.keys())}",
                    task_id=task_id
                )
            
            # 尝试打印完整响应（避免 loguru 格式化冲突）
            try:
                import json
                response_str = json.dumps(dify_output, ensure_ascii=False, indent=2)
                # 使用 opt(raw=True) 避免 loguru 格式化
                log_msg = "Dify API 响应 | task_id: " + str(task_id) + " | 响应结构: " + response_str
                from loguru import logger
                logger.opt(raw=True).info(log_msg + "\n")
            except Exception as e:
                # 如果 JSON 序列化失败，使用 str() 打印（截断）
                response_str = str(dify_output)
                if len(response_str) > 1000:
                    response_str = response_str[:1000] + "...(截断)"
                log_msg = "Dify API 响应 | task_id: " + str(task_id) + " | 响应结构（原始）: " + response_str
                from loguru import logger
                logger.opt(raw=True).info(log_msg + "\n")
                self.logger.warning(
                    f"JSON 序列化失败: {str(e)}",
                    task_id=task_id
                )
            
        except DifyAPIError as e:
            return {
                "success": False,
                "error": f"Dify API 调用失败: {str(e)}"
            }
        
        # 解析 Dify 输出
        testcases = self._parse_dify_output(dify_output, interface, task_id)
        
        # 打印解析结果
        self.logger.info(
            f"测试用例解析结果 | task_id: {task_id} | "
            f"解析到 {len(testcases)} 个测试用例",
            task_id=task_id
        )
        
        if testcases:
            # 打印测试用例详细内容（避免 loguru 格式化）
            try:
                import json
                testcases_str = json.dumps(testcases, ensure_ascii=False, indent=2)
                log_msg = "测试用例详细内容 | task_id: " + str(task_id) + " | 用例列表:\n" + testcases_str
                from loguru import logger
                logger.opt(raw=True).info(log_msg + "\n")
            except Exception as e:
                log_msg = "测试用例详细内容 | task_id: " + str(task_id) + " | 用例列表（原始）: " + str(testcases)
                from loguru import logger
                logger.opt(raw=True).info(log_msg + "\n")
        
        if not testcases:
            return {
                "success": False,
                "error": "未能生成有效的测试用例"
            }
        
        # 保存测试用例
        storage_path = self.storage.save_testcases(task_id, interface_name, testcases)
        
        # 存储到记忆管理器
        if self.memory_manager:
            for tc in testcases:
                try:
                    self.memory_manager.memorize_testcase(
                        testcase_id=tc["id"],
                        testcase_data=tc,
                        task_id=task_id
                    )
                except Exception as e:
                    self.logger.warning(
                        f"记忆存储失败: {str(e)}",
                        testcase_id=tc["id"]
                    )
        
        self.logger.info(
            f"测试用例生成完成 | "
            f"任务ID: {task_id} | "
            f"接口: {interface_name} | "
            f"用例数: {len(testcases)}",
            task_id=task_id,
            interface=interface_name,
            testcase_count=len(testcases)
        )
        
        return {
            "success": True,
            "interface_name": interface_name,
            "testcase_count": len(testcases),
            "testcases": testcases,
            "storage_path": str(storage_path)
        }
    
    def _generate_batch_testcases(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        批量生成测试用例
        
        Args:
            arguments: 工具参数
            
        Returns:
            生成结果
        """
        task_id = arguments["task_id"]
        interfaces = arguments["interfaces"]
        strategies = arguments.get("strategies", ["positive", "negative"])
        count_per_strategy = arguments.get("count_per_strategy", 3)
        
        self.logger.info(
            f"开始批量生成测试用例 | "
            f"任务ID: {task_id} | "
            f"接口数: {len(interfaces)}",
            task_id=task_id,
            interface_count=len(interfaces)
        )
        
        results = []
        total_testcases = 0
        failed_count = 0
        
        for i, interface in enumerate(interfaces, 1):
            interface_name = interface.get("name", f"interface_{i}")
            
            self.logger.debug(
                f"处理接口 {i}/{len(interfaces)}: {interface_name}",
                task_id=task_id
            )
            
            result = self._generate_testcases({
                "task_id": task_id,
                "interface": interface,
                "strategies": strategies,
                "count_per_strategy": count_per_strategy,
                "use_context_enhancement": True
            })
            
            if result.get("success"):
                total_testcases += result.get("testcase_count", 0)
                results.append({
                    "interface_name": interface_name,
                    "success": True,
                    "testcase_count": result.get("testcase_count", 0)
                })
            else:
                failed_count += 1
                results.append({
                    "interface_name": interface_name,
                    "success": False,
                    "error": result.get("error")
                })
        
        self.logger.info(
            f"批量生成完成 | "
            f"任务ID: {task_id} | "
            f"成功: {len(interfaces) - failed_count} | "
            f"失败: {failed_count} | "
            f"总用例数: {total_testcases}",
            task_id=task_id,
            total_testcases=total_testcases
        )
        
        return {
            "success": True,
            "total_interfaces": len(interfaces),
            "successful_interfaces": len(interfaces) - failed_count,
            "failed_interfaces": failed_count,
            "total_testcases": total_testcases,
            "details": results
        }
    
    def _build_workflow_input(
        self,
        interface: Dict[str, Any],
        strategies: List[str],
        count_per_strategy: int,
        enhanced_context: str
    ) -> Dict[str, Any]:
        """
        构建 Dify 工作流输入（适配 user_input 参数名）
        
        Args:
            interface: 接口信息
            strategies: 测试策略
            count_per_strategy: 每策略用例数
            enhanced_context: 增强上下文
            
        Returns:
            工作流输入参数
        """
        # 构建接口描述
        interface_desc = f"""
## 接口信息
- **名称**: {interface.get('name', '')}
- **路径**: {interface.get('path', '')}
- **方法**: {interface.get('method', '')}
- **描述**: {interface.get('description', '')}
- **基础URL**: {interface.get('base_url', '')}

## 参数
{json.dumps(interface.get('parameters', []), ensure_ascii=False, indent=2)}

## 请求体
{json.dumps(interface.get('request_body', {}), ensure_ascii=False, indent=2)}

## 响应
{json.dumps(interface.get('responses', {}), ensure_ascii=False, indent=2)}
"""
        
        # 构建策略说明
        strategy_desc = "\n".join([
            f"- {s}: {self.test_strategies.get(s, '')}"
            for s in strategies
        ])
        
        # 构建完整的用户输入
        user_query = f"""{interface_desc}

# 测试策略
{strategy_desc}

# 生成要求
- 每种策略生成 {count_per_strategy} 个测试用例
- 输出格式: JSON
"""
        
        if enhanced_context:
            user_query += f"\n\n# 参考信息\n{enhanced_context}"
        
        # 适配 Dify 工作流的 user_input 参数名
        return {
            "user_input": user_query
        }
    
    def _parse_dify_output(
        self,
        dify_output: Dict[str, Any],
        interface: Dict[str, Any],
        task_id: str
    ) -> List[Dict[str, Any]]:
        """
        解析 Dify 工作流输出
        
        Args:
            dify_output: Dify 输出
            interface: 接口信息
            task_id: 任务ID
            
        Returns:
            测试用例列表
        """
        testcases = []
        
        # 尝试从输出中提取测试用例
        # 先尝试从 Dify 的标准响应格式中提取
        output_text = None
        
        # 格式 1: {"data": {"outputs": {"text": "..."}}}
        if isinstance(dify_output, dict) and "data" in dify_output:
            outputs = dify_output.get("data", {}).get("outputs", {})
            if "text" in outputs:
                output_text = outputs["text"]
        
        # 格式 2: {"testcases": [...]}
        if output_text is None:
            output_text = dify_output.get("testcases", dify_output.get("output", ""))
        
        # 如果是字符串，尝试解析为 JSON
        if isinstance(output_text, str):
            # 先尝试直接解析
            try:
                parsed = json.loads(output_text)
                # 检查是否包含 positive/negative 策略
                if isinstance(parsed, dict) and ("positive" in parsed or "negative" in parsed):
                    output_text = parsed
                elif isinstance(parsed, list):
                    output_text = parsed
            except json.JSONDecodeError:
                pass
            
            # 如果还是字符串，尝试查找 JSON 数组
            if isinstance(output_text, str):
                try:
                    import re
                    json_match = re.search(r'\[[\s\S]*\]', output_text)
                    if json_match:
                        parsed = json.loads(json_match.group())
                        if isinstance(parsed, list):
                            output_text = parsed
                except json.JSONDecodeError:
                    pass
        
        if isinstance(output_text, list):
            # 已经是列表格式
            raw_testcases = output_text
        elif isinstance(output_text, dict):
            # 检查是否是按策略分组的格式: {"positive": [...], "negative": [...]}
            if "positive" in output_text or "negative" in output_text:
                raw_testcases = []
                # 合并所有策略的测试用例
                for strategy in ["positive", "negative", "boundary", "performance"]:
                    if strategy in output_text:
                        strategy_cases = output_text[strategy]
                        if isinstance(strategy_cases, list):
                            # 为每个用例添加策略标记
                            for tc in strategy_cases:
                                if isinstance(tc, dict):
                                    tc["strategy"] = strategy
                                    raw_testcases.append(tc)
            elif "testcases" in output_text:
                raw_testcases = output_text["testcases"]
            else:
                # 尝试从文本中提取
                raw_testcases = self._extract_testcases_from_text(str(output_text))
        else:
            # 尝试从文本中提取
            raw_testcases = self._extract_testcases_from_text(str(output_text))
        
        # 转换为标准格式
        for i, raw_tc in enumerate(raw_testcases):
            try:
                testcase = self._normalize_testcase(
                    raw_tc,
                    interface,
                    task_id,
                    index=i
                )
                testcases.append(testcase)
            except Exception as e:
                self.logger.warning(
                    f"测试用例转换失败: {str(e)}",
                    raw_testcase=raw_tc
                )
        
        return testcases
    
    def _extract_testcases_from_text(self, text: str) -> List[Dict[str, Any]]:
        """
        从文本中提取测试用例（用于非结构化输出）
        
        Args:
            text: 输出文本
            
        Returns:
            提取的测试用例列表
        """
        testcases = []
        
        # 简单的模式匹配提取
        import re
        
        # 匹配测试用例块
        pattern = r'(?:测试用例|Test Case|TC)\s*[:#]?\s*\d*[:\.]?\s*(.*?)(?=(?:测试用例|Test Case|TC)\s*[:#]?\s*\d*|$)'
        matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
        
        for match in matches:
            if match.strip():
                testcases.append({
                    "description": match.strip()[:200],
                    "raw_text": match.strip()
                })
        
        return testcases
    
    def _normalize_testcase(
        self,
        raw_tc: Dict[str, Any],
        interface: Dict[str, Any],
        task_id: str,
        index: int
    ) -> Dict[str, Any]:
        """
        将原始测试用例转换为标准格式
        
        Args:
            raw_tc: 原始测试用例
            interface: 接口信息
            task_id: 任务ID
            index: 用例索引
            
        Returns:
            标准化的测试用例
        """
        import uuid
        
        # 生成唯一 ID
        testcase_id = raw_tc.get("id", f"tc_{task_id}_{interface.get('name', 'unknown')}_{index}_{uuid.uuid4().hex[:8]}")
        
        # 构建测试用例
        # 提取请求参数（从 raw_tc.request、raw_tc.input 或直接从 raw_tc）
        request_data = raw_tc.get("request", {})
        input_data = raw_tc.get("input", {})
        
        # 决定请求体的位置（POST/PUT 用 body，GET 用 params）
        method = interface.get("method", "GET").upper()
        if method in ["POST", "PUT", "PATCH"]:
            # POST/PUT 请求，参数放在 body
            request_body = input_data if input_data else request_data.get("body", raw_tc.get("body", None))
            request_params = request_data.get("params", raw_tc.get("params", {}))
        else:
            # GET/DELETE 请求，参数放在 params
            request_body = request_data.get("body", raw_tc.get("body", None))
            request_params = input_data if input_data else request_data.get("params", raw_tc.get("params", {}))
        
        # 获取 base_url，如果为空则使用默认值
        base_url = interface.get("base_url", "") or "http://127.0.0.1:5000"
        path = interface.get("path", "")
        full_url = f"{base_url}{path}"
        
        testcase = {
            "id": testcase_id,
            "name": raw_tc.get("name", f"TestCase_{index + 1}"),
            "description": raw_tc.get("description", ""),
            "interface_name": interface.get("name", ""),
            "interface_path": path,
            "method": method,
            "base_url": base_url,
            "strategy": raw_tc.get("strategy", "positive"),
            "priority": raw_tc.get("priority", "medium"),
            "request": {
                "url": full_url,  # 完整的 URL
                "method": method,
                "headers": request_data.get("headers", raw_tc.get("headers", {})) or {"Content-Type": "application/json"},  # 默认添加 JSON 头
                "params": request_params,
                "body": request_body,
                "timeout": request_data.get("timeout", raw_tc.get("timeout", 30))
            },
            "assertions": self._build_assertions(raw_tc),
            "setup": raw_tc.get("setup", []),
            "teardown": raw_tc.get("teardown", []),
            "tags": raw_tc.get("tags", []),
            "task_id": task_id
        }
        
        return testcase
    
    def _build_assertions(self, raw_tc: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        构建断言列表
        
        Args:
            raw_tc: 原始测试用例
            
        Returns:
            断言列表
        """
        # 运算符映射：将常见的运算符名称映射为 AssertionOperator 枚举值
        operator_mapping = {
            "equals": "eq",
            "equal": "eq",
            "not_equals": "ne",
            "not_equal": "ne",
            "greater_than": "gt",
            "less_than": "lt",
            "greater_or_equal": "gte",
            "less_or_equal": "lte",
            "contains": "in",
            "not_contains": "not_in"
        }
        
        assertions = []
        
        # 从原始用例中提取断言
        raw_assertions = raw_tc.get("assertions", [])
        
        if isinstance(raw_assertions, list):
            for assertion in raw_assertions:
                if isinstance(assertion, dict):
                    # 获取原始运算符并映射
                    raw_operator = assertion.get("operator", "equals")
                    operator = operator_mapping.get(raw_operator, raw_operator)
                    
                    assertions.append({
                        "type": assertion.get("type", "status_code"),
                        "target": assertion.get("target", ""),
                        "operator": operator,  # 使用映射后的运算符
                        "expected": assertion.get("expected", ""),
                        "description": assertion.get("description", "")
                    })
        
        # 如果没有断言，添加默认的状态码断言
        if not assertions:
            expected_status = raw_tc.get("expected_status", 200)
            assertions.append({
                "type": "status_code",
                "target": "status_code",
                "operator": "eq",  # 使用正确的枚举值
                "expected": expected_status,
                "description": f"验证响应状态码为 {expected_status}"
            })
        
        return assertions
    
    def _get_test_strategies(self) -> Dict[str, Any]:
        """
        获取支持的测试策略
        
        Returns:
            策略列表
        """
        return {
            "success": True,
            "strategies": [
                {
                    "name": name,
                    "description": desc
                }
                for name, desc in self.test_strategies.items()
            ]
        }
    
    def _get_generated_testcases(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取已生成的测试用例
        
        Args:
            arguments: 工具参数
            
        Returns:
            测试用例列表
        """
        task_id = arguments["task_id"]
        interface_name = arguments.get("interface_name")
        
        try:
            if interface_name:
                testcases = self.storage.load_testcases(task_id, interface_name)
            else:
                testcases = self.storage.load_all_testcases(task_id)
            
            return {
                "success": True,
                "task_id": task_id,
                "testcase_count": len(testcases),
                "testcases": testcases
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取测试用例失败: {str(e)}"
            }


def main():
    """独立运行时的入口点"""
    generator = TestCaseGenerator(
        config={},
        logger=None,
        database=None,
        storage=None,
        memory_manager=None
    )
    generator.run()


if __name__ == "__main__":
    main()
