"""
LLM 客户端 - 统一的 Dify LLM 调用接口

为所有 MCP Server 提供统一的 LLM 调用能力
"""

import json
import time
from typing import Any, Dict, Optional

from backend.common.dify_client import DifyClient, DifyAPIError
from backend.common.prompt_builder import PromptBuilder
from backend.common.logger import get_logger


class LLMClient:
    """
    LLM 客户端
    
    封装 Dify API 调用，提供高层接口
    """
    
    def __init__(
        self,
        dify_config: Dict[str, Any],
        prompts_dir: Optional[str] = None
    ):
        """
        初始化 LLM 客户端
        
        Args:
            dify_config: Dify 配置
            prompts_dir: Prompts 目录路径
        """
        self.logger = get_logger()
        self.dify_client = DifyClient(dify_config)
        self.prompt_builder = PromptBuilder(prompts_dir)
        
        self.logger.info("LLMClient 初始化完成")
    
    def word_to_interfaces(
        self,
        word_content: Dict[str, Any],
        business_context: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Word 文档转接口规范
        
        Args:
            word_content: Word 文档内容
            business_context: 业务上下文
            task_id: 任务ID
            
        Returns:
            提取的接口列表
        """
        self.logger.info(
            f"开始 Word→接口转换 | task_id: {task_id}",
            task_id=task_id
        )
        
        try:
            # 构建 Prompt
            prompts = self.prompt_builder.build_word_to_interfaces_prompt(
                word_content=word_content,
                business_context=business_context
            )
            
            # 估算 token
            system_tokens = self.prompt_builder.estimate_token_count(prompts["system_prompt"])
            user_tokens = self.prompt_builder.estimate_token_count(prompts["user_query"])
            total_tokens = system_tokens + user_tokens
            
            self.logger.info(
                f"Prompt 构建完成 | task_id: {task_id} | "
                f"system tokens: {system_tokens} | "
                f"user tokens: {user_tokens} | "
                f"total: {total_tokens}",
                task_id=task_id
            )
            
            # 调用 Dify API
            start_time = time.time()
            
            dify_inputs = {
                "system_prompt": prompts["system_prompt"],
                "user_input": prompts["user_query"]  # Dify 工作流使用 user_input 作为参数名
            }
            
            self.logger.debug(
                f"Dify API 请求参数 | task_id: {task_id} | "
                f"参数名: {list(dify_inputs.keys())} | "
                f"system_prompt长度: {len(dify_inputs['system_prompt'])} | "
                f"user_input长度: {len(dify_inputs['user_input'])}",
                task_id=task_id
            )
            
            response = self.dify_client.call_workflow(
                inputs=dify_inputs,
                user=f"task_{task_id}" if task_id else "system"
            )
            
            elapsed = time.time() - start_time
            
            self.logger.info(
                f"Dify API 调用成功 | task_id: {task_id} | 耗时: {elapsed:.2f}s",
                task_id=task_id,
                elapsed=elapsed
            )
            
            # 解析响应
            interfaces = self._parse_interfaces_response(response)
            
            self.logger.info(
                f"接口提取完成 | task_id: {task_id} | 接口数: {len(interfaces)}",
                task_id=task_id,
                interface_count=len(interfaces)
            )
            
            return {
                "success": True,
                "interfaces": interfaces,
                "metadata": {
                    "elapsed_seconds": elapsed,
                    "estimated_tokens": total_tokens
                }
            }
        
        except DifyAPIError as e:
            self.logger.error(
                f"Dify API 调用失败 | task_id: {task_id} | 错误: {str(e)}",
                task_id=task_id,
                error=str(e)
            )
            return {
                "success": False,
                "error": f"LLM 调用失败: {str(e)}"
            }
        
        except Exception as e:
            self.logger.error(
                f"Word→接口转换失败 | task_id: {task_id} | 错误: {str(e)}",
                task_id=task_id,
                error=str(e),
                exc_info=True
            )
            return {
                "success": False,
                "error": f"转换失败: {str(e)}"
            }
    
    def generate_testcases(
        self,
        interface_spec: Dict[str, Any],
        strategies: list = None,
        count_per_strategy: int = 3,
        enhanced_context: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        生成测试用例
        
        Args:
            interface_spec: 接口规范
            strategies: 测试策略列表
            count_per_strategy: 每策略用例数
            enhanced_context: 增强上下文
            task_id: 任务ID
            
        Returns:
            生成的测试用例列表
        """
        interface_name = interface_spec.get("name", "unknown")
        
        self.logger.info(
            f"开始生成测试用例 | task_id: {task_id} | 接口: {interface_name}",
            task_id=task_id,
            interface=interface_name
        )
        
        try:
            # 构建 Prompt
            prompts = self.prompt_builder.build_generate_testcases_prompt(
                interface_spec=interface_spec,
                strategies=strategies,
                count_per_strategy=count_per_strategy,
                enhanced_context=enhanced_context
            )
            
            # 估算 token
            system_tokens = self.prompt_builder.estimate_token_count(prompts["system_prompt"])
            user_tokens = self.prompt_builder.estimate_token_count(prompts["user_query"])
            total_tokens = system_tokens + user_tokens
            
            self.logger.info(
                f"Prompt 构建完成 | task_id: {task_id} | "
                f"system tokens: {system_tokens} | "
                f"user tokens: {user_tokens} | "
                f"total: {total_tokens}",
                task_id=task_id
            )
            
            # 调用 Dify API
            start_time = time.time()
            
            dify_inputs = {
                "system_prompt": prompts["system_prompt"],
                "user_input": prompts["user_query"]  # Dify 工作流使用 user_input 作为参数名
            }
            
            self.logger.debug(
                f"Dify API 请求参数 | task_id: {task_id} | "
                f"参数名: {list(dify_inputs.keys())} | "
                f"system_prompt长度: {len(dify_inputs['system_prompt'])} | "
                f"user_input长度: {len(dify_inputs['user_input'])}",
                task_id=task_id
            )
            
            response = self.dify_client.call_workflow(
                inputs=dify_inputs,
                user=f"task_{task_id}" if task_id else "system"
            )
            
            elapsed = time.time() - start_time
            
            self.logger.info(
                f"Dify API 调用成功 | task_id: {task_id} | 耗时: {elapsed:.2f}s",
                task_id=task_id,
                elapsed=elapsed
            )
            
            # 解析响应
            testcases = self._parse_testcases_response(response, interface_spec)
            
            self.logger.info(
                f"测试用例生成完成 | task_id: {task_id} | 用例数: {len(testcases)}",
                task_id=task_id,
                testcase_count=len(testcases)
            )
            
            return {
                "success": True,
                "testcases": testcases,
                "metadata": {
                    "elapsed_seconds": elapsed,
                    "estimated_tokens": total_tokens
                }
            }
        
        except DifyAPIError as e:
            self.logger.error(
                f"Dify API 调用失败 | task_id: {task_id} | 错误: {str(e)}",
                task_id=task_id,
                error=str(e)
            )
            return {
                "success": False,
                "error": f"LLM 调用失败: {str(e)}"
            }
        
        except Exception as e:
            self.logger.error(
                f"测试用例生成失败 | task_id: {task_id} | 错误: {str(e)}",
                task_id=task_id,
                error=str(e),
                exc_info=True
            )
            return {
                "success": False,
                "error": f"生成失败: {str(e)}"
            }
    
    def _parse_interfaces_response(self, response: Dict[str, Any]) -> list:
        """
        解析接口响应
        
        Args:
            response: Dify API 响应
            
        Returns:
            接口列表
        """
        # 打印完整响应结构
        import json
        self.logger.info(
            f"Dify API 原始响应 | 响应结构: {json.dumps(response, ensure_ascii=False, indent=2)}"
        )
        
        # 从响应中提取 JSON
        output = response.get("data", {}).get("outputs", {})
        
        self.logger.info(
            f"Dify API outputs 字段 | 可用字段: {list(output.keys())}"
        )
        
        # 可能的字段名
        for field in ["interfaces", "result", "output", "text"]:
            if field in output:
                content = output[field]
                self.logger.info(
                    f"找到字段 '{field}' | 类型: {type(content).__name__} | 内容长度: {len(str(content))}"
                )
                break
        else:
            content = str(output)
            self.logger.warning(
                f"未找到预期字段，使用整个 output | 内容: {content[:500]}"
            )
        
        # 尝试解析 JSON
        if isinstance(content, str):
            self.logger.info(f"尝试从字符串解析 JSON | 内容长度: {len(content)}")
            
            try:
                # 尝试直接解析整个 JSON
                parsed = json.loads(content)
                
                # 情兵1：直接包含 interfaces 字段
                if "interfaces" in parsed:
                    self.logger.info(f"✅ 直接提取 interfaces | 接口数: {len(parsed['interfaces'])}")
                    return parsed["interfaces"]
                
                # 情兵2：OpenAPI 格式，需要转换
                elif "openapi" in parsed or "swagger" in parsed:
                    self.logger.info("检测到 OpenAPI 格式，开始转换...")
                    interfaces = self._convert_openapi_to_interfaces(parsed)
                    self.logger.info(f"✅ OpenAPI 转换完成 | 接口数: {len(interfaces)}")
                    return interfaces
                
                else:
                    self.logger.warning(f"未识别的 JSON 格式 | 顶层字段: {list(parsed.keys())}")
                    
            except json.JSONDecodeError as e:
                self.logger.error(f"❌ JSON 解析失败: {str(e)} | 内容预览: {content[:200]}")
        
        elif isinstance(content, dict):
            self.logger.info(f"内容已是字典类型 | 字段: {list(content.keys())}")
            if "interfaces" in content:
                self.logger.info(f"✅ 直接提取 | 接口数: {len(content['interfaces'])}")
                return content["interfaces"]
            else:
                self.logger.warning(f"字典中未找到 'interfaces' 字段 | 可用字段: {list(content.keys())}")
        
        # 解析失败，返回空列表
        self.logger.warning("无法从响应中提取接口列表")
        return []
    
    def _convert_openapi_to_interfaces(self, openapi_spec: Dict[str, Any]) -> list:
        """
        将 OpenAPI 规范转换为内部接口格式
        
        Args:
            openapi_spec: OpenAPI 规范
            
        Returns:
            接口列表
        """
        interfaces = []
        paths = openapi_spec.get("paths", {})
        
        for path, methods in paths.items():
            for method, spec in methods.items():
                if method.upper() not in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                    continue
                
                # 提取接口信息
                interface = {
                    "name": spec.get("summary", spec.get("operationId", f"{method.upper()} {path}")),
                    "method": method.upper(),
                    "path": path,
                    "description": spec.get("description", ""),
                    "parameters": [],
                    "request_body": None,
                    "responses": {}
                }
                
                # 提取路径参数和查询参数
                for param in spec.get("parameters", []):
                    interface["parameters"].append({
                        "name": param.get("name"),
                        "type": param.get("schema", {}).get("type", "string"),
                        "required": param.get("required", False),
                        "description": param.get("description", ""),
                        "in": param.get("in", "query")
                    })
                
                # 提取请求体
                if "requestBody" in spec:
                    req_body = spec["requestBody"]
                    content = req_body.get("content", {})
                    if "application/json" in content:
                        schema = content["application/json"].get("schema", {})
                        interface["request_body"] = self._extract_schema_properties(schema, openapi_spec)
                
                # 提取响应
                for status_code, response_spec in spec.get("responses", {}).items():
                    content = response_spec.get("content", {})
                    if "application/json" in content:
                        schema = content["application/json"].get("schema", {})
                        interface["responses"][status_code] = {
                            "description": response_spec.get("description", ""),
                            "schema": self._extract_schema_properties(schema, openapi_spec)
                        }
                
                interfaces.append(interface)
        
        return interfaces
    
    def _extract_schema_properties(self, schema: Dict[str, Any], openapi_spec: Dict[str, Any]) -> Dict[str, Any]:
        """
        提取 Schema 属性，支持 $ref 引用
        
        Args:
            schema: Schema 定义
            openapi_spec: 完整的 OpenAPI 规范
            
        Returns:
            Schema 属性
        """
        # 处理 $ref 引用
        if "$ref" in schema:
            ref_path = schema["$ref"].split("/")
            ref_schema = openapi_spec
            for part in ref_path:
                if part == "#":
                    continue
                ref_schema = ref_schema.get(part, {})
            schema = ref_schema
        
        # 提取属性
        properties = {}
        for prop_name, prop_spec in schema.get("properties", {}).items():
            properties[prop_name] = {
                "type": prop_spec.get("type", "string"),
                "description": prop_spec.get("description", ""),
                "required": prop_name in schema.get("required", []),
                "enum": prop_spec.get("enum"),
                "example": prop_spec.get("example")
            }
        
        return {
            "type": schema.get("type", "object"),
            "properties": properties,
            "required": schema.get("required", []),
            "example": schema.get("example")
        }
    
    def _parse_testcases_response(
        self,
        response: Dict[str, Any],
        interface_spec: Dict[str, Any]
    ) -> list:
        """
        解析测试用例响应
        
        Args:
            response: Dify API 响应
            interface_spec: 接口规范
            
        Returns:
            测试用例列表
        """
        # 从响应中提取 JSON
        output = response.get("data", {}).get("outputs", {})
        
        # 可能的字段名
        for field in ["testcases", "result", "output", "text"]:
            if field in output:
                content = output[field]
                break
        else:
            content = str(output)
        
        # 尝试解析 JSON
        if isinstance(content, str):
            # 提取 JSON 部分
            import re
            json_match = re.search(r'\{[\s\S]*"testcases"[\s\S]*\[[\s\S]*\][\s\S]*\}', content)
            if json_match:
                try:
                    parsed = json.loads(json_match.group())
                    if "testcases" in parsed:
                        return parsed["testcases"]
                except json.JSONDecodeError:
                    pass
        
        elif isinstance(content, dict):
            if "testcases" in content:
                return content["testcases"]
        
        # 解析失败，返回空列表
        self.logger.warning("无法从响应中提取测试用例列表")
        return []


def get_llm_client(dify_config: Dict[str, Any], prompts_dir: Optional[str] = None) -> LLMClient:
    """
    获取 LLMClient 实例（工厂函数）
    
    Args:
        dify_config: Dify 配置
        prompts_dir: Prompts 目录路径
        
    Returns:
        LLMClient 实例
    """
    return LLMClient(dify_config, prompts_dir)
