"""
报告分析 MCP Server

负责使用 LLM 分析测试报告，提供深入的失败原因分析、接口质量评估等。
"""

import json
from typing import Any, Dict, List, Optional
from datetime import datetime

from backend.mcp_servers.base import MCPServer
from backend.common.logger import Logger
from backend.common.database import Database
from backend.common.storage import StorageManager
from backend.common.llm_client import LLMClient


class ReportAnalyzer(MCPServer):
    """
    报告分析 MCP Server
    
    功能：
    - 使用 LLM 分析测试报告
    - 提供失败原因分析
    - 评估接口质量
    - 评价测试覆盖度
    - 给出改进建议
    """
    
    def __init__(self, config: Dict[str, Any], logger: Logger, 
                 database: Database, storage: StorageManager):
        super().__init__("report_analyzer", "1.0.0")
        self.config = config
        self.database = database
        self.storage = storage
        self.logger = logger
        
        # 初始化 LLM 客户端
        self.llm_client: Optional[LLMClient] = None
        self._init_llm_client()
        
        self.logger.info(
            f"ReportAnalyzer 初始化完成 | LLM可用: {self.llm_client is not None}",
            server="report_analyzer"
        )
    
    def _init_llm_client(self):
        """初始化 LLM 客户端"""
        try:
            from backend.common.llm_client import get_llm_client
            self.llm_client = get_llm_client(self.config)
            self.logger.info("LLM 客户端初始化成功", server="report_analyzer")
        except Exception as e:
            self.logger.warning(
                f"LLM 客户端初始化失败: {str(e)}",
                server="report_analyzer"
            )
            self.llm_client = None
    
    def get_tools(self) -> List[Dict[str, Any]]:
        """返回支持的工具列表"""
        return [
            {
                "name": "analyze_report",
                "description": "使用 LLM 分析测试报告，提供深入分析和建议",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "任务ID"
                        },
                        "report_data": {
                            "type": "object",
                            "description": "测试报告数据（JSON格式）"
                        }
                    },
                    "required": ["task_id", "report_data"]
                }
            }
        ]
    
    def handle_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具调用"""
        try:
            if tool_name == "analyze_report":
                return self._analyze_report(arguments)
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
    
    def _analyze_report(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        分析测试报告
        
        Args:
            arguments: 工具参数
            
        Returns:
            分析结果
        """
        task_id = arguments["task_id"]
        report_data = arguments["report_data"]
        
        self.logger.info(
            f"开始分析测试报告 | task_id: {task_id}",
            task_id=task_id
        )
        
        # 检查 LLM 客户端是否可用
        if not self.llm_client:
            return {
                "success": False,
                "error": "LLM 客户端未初始化，请检查 config/dify.toml 配置"
            }
        
        # 构建分析 Prompt
        prompt = self._build_analysis_prompt(report_data)
        
        # 调用 LLM
        try:
            # 使用 user_input 参数名（根据 dify.toml 配置）
            user_input_key = self.config.get("user_input_key", "user_input")
            
            self.logger.info(
                f"调用 LLM 分析报告 | task_id: {task_id} | 参数名: {user_input_key}",
                task_id=task_id
            )
            
            # 直接调用 dify_client.call_workflow
            response = self.llm_client.dify_client.call_workflow(
                inputs={user_input_key: prompt},
                user=f"task_{task_id}"
            )
            
            # 直接提取分析结果（Dify 响应格式为 {"data": {"outputs": {"text": "..."}}}）
            analysis_markdown = self._extract_analysis_result(response)
            
            # 检查是否成功提取到内容
            if analysis_markdown and not analysis_markdown.startswith("# 分析结果\n\n未能"):
                self.logger.info(
                    f"报告分析完成 | task_id: {task_id}",
                    task_id=task_id
                )
                
                return {
                    "success": True,
                    "analysis_markdown": analysis_markdown
                }
            else:
                # 提取失败
                error_msg = "未能从响应中提取分析内容"
                self.logger.error(
                    f"LLM 分析失败 | task_id: {task_id} | 错误: {error_msg}",
                    task_id=task_id
                )
                
                return {
                    "success": False,
                    "error": error_msg
                }
        
        except Exception as e:
            self.logger.error(
                f"LLM 调用异常 | task_id: {task_id} | 错误: {str(e)}",
                task_id=task_id,
                exc_info=True
            )
            return {
                "success": False,
                "error": f"LLM 调用失败: {str(e)}"
            }
    
    def _build_analysis_prompt(self, report_data: Dict[str, Any]) -> str:
        """
        构建分析 Prompt
        
        Args:
            report_data: 测试报告数据
            
        Returns:
            Prompt 文本
        """
        # 提取关键信息（避免发送过多数据）
        summary = {
            "task_id": report_data.get("task_id"),
            "total_count": report_data.get("total_count", 0),
            "passed_count": report_data.get("passed_count", 0),
            "failed_count": report_data.get("failed_count", 0),
            "error_count": report_data.get("error_count", 0),
            "pass_rate": report_data.get("pass_rate", 0),
            "total_duration": report_data.get("total_duration", 0)
        }
        
        # 提取失败和错误的测试用例详情
        failed_cases = []
        testcase_results = report_data.get("testcase_results", [])
        
        for result in testcase_results:
            if result.get("status") in ["failed", "error"]:
                failed_cases.append({
                    "testcase_id": result.get("testcase_id"),
                    "interface_name": result.get("interface_name"),
                    "status": result.get("status"),
                    "error_message": result.get("error_message"),
                    "request": result.get("request"),
                    "response": result.get("response"),
                    "duration": result.get("duration")
                })
        
        # 提取慢速用例
        slowest_testcases = report_data.get("slowest_testcases", [])[:5]
        
        # 提取错误模式
        error_patterns = report_data.get("error_patterns", [])[:5]
        
        # 构建 JSON 数据
        analysis_data = {
            "summary": summary,
            "failed_cases": failed_cases,
            "slowest_testcases": slowest_testcases,
            "error_patterns": error_patterns
        }
        
        # 转换为 JSON 字符串
        report_json = json.dumps(analysis_data, ensure_ascii=False, indent=2)
        
        # 构建 Prompt
        prompt = f"""你是一个专业的测试分析师，请对以下测试报告进行深入分析：

## 测试报告数据
```json
{report_json}
```

## 分析要求
请从以下四个维度进行分析，并以 Markdown 格式输出（使用清晰的章节标题）：

### 1. 失败原因分析
- 分析为什么测试失败
- 识别共性问题和模式
- 给出可能的根本原因
- 提供修复建议

### 2. 接口质量评估
- 评估接口设计的合理性
- 分析响应时间和性能
- 评价错误处理机制
- 指出潜在的设计缺陷

### 3. 测试覆盖度评价
- 分析测试用例是否充分
- 识别缺失的测试场景
- 建议需要补充的边界用例
- 评估测试策略的完整性

### 4. 改进建议
- 针对失败用例给出具体的修复建议
- 针对接口设计给出优化方向
- 针对测试用例给出增强建议
- 提供最佳实践参考

请确保分析内容：
- 结构清晰，使用 Markdown 标题和列表
- 结论明确，建议可操作
- 重点突出，避免空泛描述
- 专业准确，基于数据分析
"""
        
        return prompt
    
    def _extract_analysis_result(self, response: Dict[str, Any]) -> str:
        """
        从 LLM 响应中提取分析结果
        
        Args:
            response: LLM 响应
            
        Returns:
            Markdown 格式的分析内容
        """
        # 根据 Dify 响应格式提取内容
        # 响应格式: {"success": True, "data": {"outputs": {"text": "..."}}}
        
        try:
            data = response.get("data", {})
            outputs = data.get("outputs", {})
            text = outputs.get("text", "")
            
            if not text:
                # 尝试其他可能的路径
                text = response.get("text", "")
                if not text:
                    text = response.get("result", "")
            
            if text:
                return text
            else:
                self.logger.warning("LLM 响应中未找到文本内容")
                return "# 分析结果\n\n未能从 LLM 响应中提取分析内容。"
        
        except Exception as e:
            self.logger.error(f"提取分析结果失败: {str(e)}")
            return f"# 分析结果\n\n提取分析内容时发生错误: {str(e)}"
    
    def cleanup(self):
        """清理资源"""
        if self.llm_client:
            try:
                # LLM 客户端通常无需清理
                pass
            except Exception as e:
                self.logger.warning(f"LLM 客户端清理失败: {str(e)}")
        
        self.logger.info("ReportAnalyzer 资源已清理", server="report_analyzer")
