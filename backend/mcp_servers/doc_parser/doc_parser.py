"""
API 文档解析 MCP Server

负责解析各种格式的 API 文档，提取接口信息，构建知识库。
支持的格式：
- OpenAPI/Swagger (YAML/JSON)
- Postman Collection
- HAR 文件
"""

import json
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.mcp_servers.base import MCPServer, MCPError
from backend.common.logger import Logger
from backend.common.database import Database
from backend.common.storage import StorageManager
from backend.common.llm_client import LLMClient


class DocumentParser(MCPServer):
    """
    API 文档解析 MCP Server
    
    功能：
    - 解析 OpenAPI/Swagger 规范文档
    - 解析 Postman Collection
    - 解析 HAR (HTTP Archive) 文件
    - 提取接口元数据（路径、方法、参数、响应等）
    - 构建结构化的接口知识
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        logger: Logger,
        database: Database,
        storage: StorageManager,
        llm_client: Optional[LLMClient] = None
    ):
        super().__init__("doc_parser", "1.0.0")
        self.config = config
        self.database = database
        self.storage = storage
        self.llm_client = llm_client  # LLM 客户端（用于 Word 文档转接口）
        # 覆盖基类的 logger
        self.logger = logger
        
        self.logger.info(
            f"DocumentParser 初始化完成 | LLM支持: {llm_client is not None}",
            server="doc_parser",
            llm_enabled=llm_client is not None
        )
    
    def get_tools(self) -> List[Dict[str, Any]]:
        """返回支持的工具列表"""
        return [
            {
                "name": "parse_document",
                "description": "自动识别并解析文档（支持OpenAPI/Swagger、Postman、HAR、Word）",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "任务ID"
                        },
                        "document_path": {
                            "type": "string",
                            "description": "文档文件路径"
                        },
                        "parse_strategy": {
                            "type": "string",
                            "enum": ["auto", "openapi", "postman", "har", "word"],
                            "description": "解析策略：auto自动识别，或指定格式，默认auto"
                        }
                    },
                    "required": ["document_path"]
                }
            },
            {
                "name": "parse_openapi",
                "description": "解析 OpenAPI/Swagger 规范文档",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "任务ID"
                        },
                        "file_path": {
                            "type": "string",
                            "description": "OpenAPI 文档路径"
                        },
                        "content": {
                            "type": "string",
                            "description": "OpenAPI 文档内容（与 file_path 二选一）"
                        },
                        "base_url": {
                            "type": "string",
                            "description": "API 基础 URL（可选，覆盖文档中的 servers）"
                        }
                    },
                    "required": ["task_id"]
                }
            },
            {
                "name": "parse_postman",
                "description": "解析 Postman Collection",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "任务ID"
                        },
                        "file_path": {
                            "type": "string",
                            "description": "Postman Collection 文件路径"
                        },
                        "content": {
                            "type": "string",
                            "description": "Postman Collection JSON 内容"
                        }
                    },
                    "required": ["task_id"]
                }
            },
            {
                "name": "parse_har",
                "description": "解析 HAR (HTTP Archive) 文件",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "任务ID"
                        },
                        "file_path": {
                            "type": "string",
                            "description": "HAR 文件路径"
                        },
                        "content": {
                            "type": "string",
                            "description": "HAR JSON 内容"
                        },
                        "filter_domain": {
                            "type": "string",
                            "description": "仅保留指定域名的请求（可选）"
                        }
                    },
                    "required": ["task_id"]
                }
            },
            {
                "name": "get_interfaces",
                "description": "获取已解析的接口列表",
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
            },
            {
                "name": "parse_word",
                "description": "解析Word文档并提取文本内容",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "任务ID"
                        },
                        "file_path": {
                            "type": "string",
                            "description": "Word文档路径"
                        },
                        "extract_mode": {
                            "type": "string",
                            "enum": ["text", "structured", "tables"],
                            "description": "提取模式：纯文本/结构化内容/表格，默认structured"
                        }
                    },
                    "required": ["task_id", "file_path"]
                }
            }
        ]
    
    def handle_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具调用"""
        try:
            if tool_name == "parse_document":
                return self._parse_document(arguments)
            
            elif tool_name == "parse_openapi":
                return self._parse_openapi(arguments)
            
            elif tool_name == "parse_postman":
                return self._parse_postman(arguments)
            
            elif tool_name == "parse_har":
                return self._parse_har(arguments)
            
            elif tool_name == "get_interfaces":
                return self._get_interfaces(arguments)
            
            elif tool_name == "parse_word":
                return self._parse_word(arguments)
            
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
    
    def _parse_document(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        自动识别并解析文档
        
        Args:
            arguments: 工具参数
            
        Returns:
            解析结果
        """
        document_path = arguments.get("document_path")
        parse_strategy = arguments.get("parse_strategy", "auto")
        task_id = arguments.get("task_id")
        
        if not document_path:
            return {
                "success": False,
                "error": "缺少必需参数: document_path"
            }
        
        self.logger.info(
            f"开始解析文档 | 路径: {document_path} | 策略: {parse_strategy}",
            document_path=document_path,
            parse_strategy=parse_strategy
        )
        
        # 识别文档类型
        file_path = Path(document_path)
        if not file_path.exists():
            return {
                "success": False,
                "error": f"文件不存在: {document_path}"
            }
        
        file_ext = file_path.suffix.lower()
        
        # 根据策略或文件扩展名选择解析器
        if parse_strategy == "auto":
            # 自动识别
            if file_ext in [".yaml", ".yml", ".json"]:
                # 尝试读取内容判断类型
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                    
                    # 解析为字典
                    if content.startswith('{'):
                        data = json.loads(content)
                    else:
                        data = yaml.safe_load(content)
                    
                    # 判断文档类型
                    if "openapi" in data or "swagger" in data:
                        parse_strategy = "openapi"
                    elif "info" in data and "item" in data:  # Postman Collection
                        parse_strategy = "postman"
                    elif "log" in data and "entries" in data.get("log", {}):  # HAR
                        parse_strategy = "har"
                    else:
                        parse_strategy = "openapi"  # 默认尝试 OpenAPI
                
                except Exception as e:
                    self.logger.warning(
                        f"自动识别失败，默认使用 OpenAPI 解析器 | 错误: {str(e)}",
                        error=str(e)
                    )
                    parse_strategy = "openapi"
            
            elif file_ext in [".docx", ".doc"]:
                parse_strategy = "word"
            
            elif file_ext == ".har":
                parse_strategy = "har"
            
            else:
                return {
                    "success": False,
                    "error": f"不支持的文件格式: {file_ext}"
                }
        
        self.logger.info(
            f"文档类型识别完成 | 使用解析器: {parse_strategy}",
            parse_strategy=parse_strategy
        )
        
        # 调用相应的解析器
        if parse_strategy == "openapi":
            return self._parse_openapi({
                "task_id": task_id,
                "file_path": str(document_path)
            })
        
        elif parse_strategy == "postman":
            return self._parse_postman({
                "task_id": task_id,
                "file_path": str(document_path)
            })
        
        elif parse_strategy == "har":
            return self._parse_har({
                "task_id": task_id,
                "file_path": str(document_path)
            })
        
        elif parse_strategy == "word":
            result = self._parse_word({
                "task_id": task_id,
                "file_path": str(document_path),
                "extract_mode": "structured"
            })
            # 转换Word结果为interfaces格式
            return self._convert_word_to_interfaces(result)
        
        else:
            return {
                "success": False,
                "error": f"不支持的解析策略: {parse_strategy}"
            }
    
    def _convert_word_to_interfaces(self, word_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        将Word文档解析结果转换为接口格式
        
        使用 LLM 将 Word 文档内容转换为 API 接口规范
        
        Args:
            word_result: Word解析结果
            
        Returns:
            包含interfaces字段的结果
        """
        if not word_result.get("success"):
            return word_result
        
        task_id = word_result.get("task_id")
        
        # 检查是否有 LLM 客户端
        if not self.llm_client:
            self.logger.warning(
                f"Word文档需要 LLM 处理，但未配置 LLM 客户端 | task_id: {task_id}",
                task_id=task_id
            )
            # 返回空接口列表，但标记需要 Dify 处理
            word_result["interfaces"] = []
            word_result["is_word_document"] = True
            word_result["requires_dify_processing"] = True
            return word_result
        
        self.logger.info(
            f"开始使用 LLM 转换 Word 文档为接口 | task_id: {task_id}",
            task_id=task_id
        )
        
        try:
            # 提取 Word 内容
            word_content = word_result.get("content", {})
            
            # 调用 LLM 转换
            llm_result = self.llm_client.word_to_interfaces(
                word_content=word_content,
                business_context=None,  # 可从文档标题提取
                task_id=task_id
            )
            
            if not llm_result.get("success"):
                self.logger.error(
                    f"LLM 转换 Word 文档失败 | task_id: {task_id} | 错误: {llm_result.get('error')}",
                    task_id=task_id,
                    error=llm_result.get("error")
                )
                return {
                    "success": False,
                    "error": f"Word 文档转接口失败: {llm_result.get('error')}"
                }
            
            interfaces = llm_result.get("interfaces", [])
            metadata = llm_result.get("metadata", {})
            
            self.logger.info(
                f"LLM 转换 Word 文档完成 | task_id: {task_id} | "
                f"接口数: {len(interfaces)} | "
                f"耗时: {metadata.get('elapsed_seconds', 0):.2f}s | "
                f"Token估算: {metadata.get('estimated_tokens', 0)}",
                task_id=task_id,
                interface_count=len(interfaces),
                elapsed=metadata.get('elapsed_seconds'),
                tokens=metadata.get('estimated_tokens')
            )
            
            # 添加接口列表和标记
            word_result["interfaces"] = interfaces
            word_result["is_word_document"] = True
            word_result["llm_processed"] = True
            word_result["llm_metadata"] = metadata
            
            # 如果提取到了接口，更新 success 状态
            if interfaces:
                word_result["success"] = True
            
            return word_result
        
        except Exception as e:
            self.logger.error(
                f"Word 文档转接口处理异常 | task_id: {task_id} | 错误: {str(e)}",
                task_id=task_id,
                error=str(e),
                exc_info=True
            )
            return {
                "success": False,
                "error": f"Word 文档处理异常: {str(e)}"
            }
    
    def _parse_openapi(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析 OpenAPI/Swagger 文档
        
        Args:
            arguments: 工具参数
            
        Returns:
            解析结果
        """
        task_id = arguments["task_id"]
        file_path = arguments.get("file_path")
        content = arguments.get("content")
        base_url = arguments.get("base_url")
        
        self.logger.info(
            f"开始解析 OpenAPI 文档 | 任务ID: {task_id}",
            task_id=task_id
        )
        
        # 获取文档内容
        if content:
            doc_content = content
        elif file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    doc_content = f.read()
            except Exception as e:
                return {
                    "success": False,
                    "error": f"读取文件失败: {str(e)}"
                }
        else:
            return {
                "success": False,
                "error": "请提供 file_path 或 content 参数"
            }
        
        # 解析文档（支持 YAML 和 JSON）
        try:
            if doc_content.strip().startswith('{'):
                spec = json.loads(doc_content)
            else:
                spec = yaml.safe_load(doc_content)
        except Exception as e:
            return {
                "success": False,
                "error": f"文档解析失败: {str(e)}"
            }
        
        # 检测 OpenAPI 版本
        openapi_version = spec.get("openapi", spec.get("swagger", "unknown"))
        
        # 提取接口信息
        interfaces = []
        
        # 获取基础 URL
        if base_url:
            api_base_url = base_url
        elif "servers" in spec:
            api_base_url = spec["servers"][0].get("url", "")
        elif "host" in spec:  # Swagger 2.0
            schemes = spec.get("schemes", ["https"])
            api_base_url = f"{schemes[0]}://{spec['host']}{spec.get('basePath', '')}"
        else:
            api_base_url = ""
        
        # 遍历所有路径
        paths = spec.get("paths", {})
        for path, path_item in paths.items():
            for method, operation in path_item.items():
                if method in ["get", "post", "put", "delete", "patch", "options", "head"]:
                    interface = self._extract_interface(
                        path=path,
                        method=method.upper(),
                        operation=operation,
                        base_url=api_base_url,
                        spec=spec
                    )
                    interfaces.append(interface)
        
        # 保存解析结果
        result = {
            "task_id": task_id,
            "openapi_version": openapi_version,
            "base_url": api_base_url,
            "interface_count": len(interfaces),
            "interfaces": interfaces
        }
        
        # 存储到文件系统
        storage_path = self.storage.save_interfaces(task_id, interfaces)
        
        self.logger.info(
            f"OpenAPI 文档解析完成 | "
            f"任务ID: {task_id} | "
            f"版本: {openapi_version} | "
            f"接口数: {len(interfaces)}",
            task_id=task_id,
            interface_count=len(interfaces)
        )
        
        return {
            "success": True,
            "result": result,
            "storage_path": str(storage_path)
        }
    
    def _extract_interface(
        self,
        path: str,
        method: str,
        operation: Dict[str, Any],
        base_url: str,
        spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        从 OpenAPI 操作中提取接口信息
        
        Args:
            path: API 路径
            method: HTTP 方法
            operation: OpenAPI 操作对象
            base_url: 基础 URL
            spec: 完整的 OpenAPI 规范
            
        Returns:
            接口信息字典
        """
        interface = {
            "name": operation.get("operationId", f"{method}_{path.replace('/', '_')}"),
            "path": path,
            "method": method,
            "base_url": base_url,
            "full_url": f"{base_url}{path}",
            "summary": operation.get("summary", ""),
            "description": operation.get("description", ""),
            "tags": operation.get("tags", []),
            "parameters": [],
            "request_body": None,
            "responses": {}
        }
        
        # 提取参数
        for param in operation.get("parameters", []):
            param_info = {
                "name": param.get("name"),
                "in": param.get("in"),  # path, query, header, cookie
                "required": param.get("required", False),
                "description": param.get("description", ""),
                "schema": param.get("schema", {})
            }
            interface["parameters"].append(param_info)
        
        # 提取请求体（OpenAPI 3.x）
        if "requestBody" in operation:
            request_body = operation["requestBody"]
            content = request_body.get("content", {})
            
            # 优先使用 application/json
            if "application/json" in content:
                schema = content["application/json"].get("schema", {})
                interface["request_body"] = {
                    "content_type": "application/json",
                    "required": request_body.get("required", False),
                    "schema": self._resolve_schema(schema, spec)
                }
            elif content:
                # 使用第一个可用的 content type
                content_type = list(content.keys())[0]
                schema = content[content_type].get("schema", {})
                interface["request_body"] = {
                    "content_type": content_type,
                    "required": request_body.get("required", False),
                    "schema": self._resolve_schema(schema, spec)
                }
        
        # 提取响应
        for status_code, response in operation.get("responses", {}).items():
            response_info = {
                "description": response.get("description", ""),
                "schema": None
            }
            
            # OpenAPI 3.x
            if "content" in response:
                content = response["content"]
                if "application/json" in content:
                    schema = content["application/json"].get("schema", {})
                    response_info["schema"] = self._resolve_schema(schema, spec)
            # Swagger 2.0
            elif "schema" in response:
                response_info["schema"] = self._resolve_schema(response["schema"], spec)
            
            interface["responses"][status_code] = response_info
        
        return interface
    
    def _resolve_schema(
        self,
        schema: Dict[str, Any],
        spec: Dict[str, Any],
        depth: int = 0
    ) -> Dict[str, Any]:
        """
        解析 Schema 引用
        
        Args:
            schema: Schema 对象
            spec: 完整的 OpenAPI 规范
            depth: 递归深度（防止无限递归）
            
        Returns:
            解析后的 Schema
        """
        if depth > 10:  # 防止无限递归
            return schema
        
        # 处理 $ref 引用
        if "$ref" in schema:
            ref = schema["$ref"]
            # 解析引用路径，如 "#/components/schemas/User"
            if ref.startswith("#/"):
                parts = ref[2:].split("/")
                resolved = spec
                for part in parts:
                    resolved = resolved.get(part, {})
                return self._resolve_schema(resolved, spec, depth + 1)
        
        # 处理 allOf、oneOf、anyOf
        for key in ["allOf", "oneOf", "anyOf"]:
            if key in schema:
                merged = {}
                for sub_schema in schema[key]:
                    resolved = self._resolve_schema(sub_schema, spec, depth + 1)
                    merged.update(resolved)
                return merged
        
        # 处理数组类型
        if schema.get("type") == "array" and "items" in schema:
            schema["items"] = self._resolve_schema(schema["items"], spec, depth + 1)
        
        # 处理对象类型
        if schema.get("type") == "object" and "properties" in schema:
            for prop_name, prop_schema in schema["properties"].items():
                schema["properties"][prop_name] = self._resolve_schema(
                    prop_schema, spec, depth + 1
                )
        
        return schema
    
    def _parse_postman(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析 Postman Collection
        
        Args:
            arguments: 工具参数
            
        Returns:
            解析结果
        """
        task_id = arguments["task_id"]
        file_path = arguments.get("file_path")
        content = arguments.get("content")
        
        self.logger.info(
            f"开始解析 Postman Collection | 任务ID: {task_id}",
            task_id=task_id
        )
        
        # 获取文档内容
        if content:
            doc_content = content
        elif file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    doc_content = f.read()
            except Exception as e:
                return {
                    "success": False,
                    "error": f"读取文件失败: {str(e)}"
                }
        else:
            return {
                "success": False,
                "error": "请提供 file_path 或 content 参数"
            }
        
        # 解析 JSON
        try:
            collection = json.loads(doc_content)
        except Exception as e:
            return {
                "success": False,
                "error": f"JSON 解析失败: {str(e)}"
            }
        
        # 提取接口信息
        interfaces = []
        self._extract_postman_items(collection.get("item", []), interfaces)
        
        # 保存解析结果
        result = {
            "task_id": task_id,
            "collection_name": collection.get("info", {}).get("name", "Unknown"),
            "interface_count": len(interfaces),
            "interfaces": interfaces
        }
        
        # 存储到文件系统
        storage_path = self.storage.save_interfaces(task_id, interfaces)
        
        self.logger.info(
            f"Postman Collection 解析完成 | "
            f"任务ID: {task_id} | "
            f"集合: {result['collection_name']} | "
            f"接口数: {len(interfaces)}",
            task_id=task_id,
            interface_count=len(interfaces)
        )
        
        return {
            "success": True,
            "result": result,
            "storage_path": str(storage_path)
        }
    
    def _extract_postman_items(
        self,
        items: List[Dict[str, Any]],
        interfaces: List[Dict[str, Any]],
        folder_path: str = ""
    ):
        """
        递归提取 Postman Collection 中的请求
        
        Args:
            items: Postman items 列表
            interfaces: 接口列表（会被修改）
            folder_path: 当前文件夹路径
        """
        for item in items:
            # 如果是文件夹，递归处理
            if "item" in item:
                sub_folder = f"{folder_path}/{item.get('name', '')}" if folder_path else item.get('name', '')
                self._extract_postman_items(item["item"], interfaces, sub_folder)
            
            # 如果是请求
            elif "request" in item:
                request = item["request"]
                url = request.get("url", {})
                
                # 处理 URL
                if isinstance(url, str):
                    full_url = url
                    path = url
                else:
                    raw_url = url.get("raw", "")
                    path = "/" + "/".join(url.get("path", []))
                    full_url = raw_url
                
                interface = {
                    "name": item.get("name", ""),
                    "path": path,
                    "method": request.get("method", "GET"),
                    "full_url": full_url,
                    "description": item.get("description", ""),
                    "folder": folder_path,
                    "parameters": [],
                    "request_body": None,
                    "headers": []
                }
                
                # 提取查询参数
                if isinstance(url, dict):
                    for query in url.get("query", []):
                        interface["parameters"].append({
                            "name": query.get("key"),
                            "in": "query",
                            "value": query.get("value"),
                            "description": query.get("description", "")
                        })
                
                # 提取请求头
                for header in request.get("header", []):
                    interface["headers"].append({
                        "name": header.get("key"),
                        "value": header.get("value"),
                        "description": header.get("description", "")
                    })
                
                # 提取请求体
                body = request.get("body")
                if body:
                    mode = body.get("mode")
                    if mode == "raw":
                        interface["request_body"] = {
                            "mode": "raw",
                            "content": body.get("raw", ""),
                            "options": body.get("options", {})
                        }
                    elif mode == "formdata":
                        interface["request_body"] = {
                            "mode": "formdata",
                            "fields": body.get("formdata", [])
                        }
                    elif mode == "urlencoded":
                        interface["request_body"] = {
                            "mode": "urlencoded",
                            "fields": body.get("urlencoded", [])
                        }
                
                interfaces.append(interface)
    
    def _parse_har(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析 HAR (HTTP Archive) 文件
        
        Args:
            arguments: 工具参数
            
        Returns:
            解析结果
        """
        task_id = arguments["task_id"]
        file_path = arguments.get("file_path")
        content = arguments.get("content")
        filter_domain = arguments.get("filter_domain")
        
        self.logger.info(
            f"开始解析 HAR 文件 | 任务ID: {task_id}",
            task_id=task_id
        )
        
        # 获取文档内容
        if content:
            doc_content = content
        elif file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    doc_content = f.read()
            except Exception as e:
                return {
                    "success": False,
                    "error": f"读取文件失败: {str(e)}"
                }
        else:
            return {
                "success": False,
                "error": "请提供 file_path 或 content 参数"
            }
        
        # 解析 JSON
        try:
            har = json.loads(doc_content)
        except Exception as e:
            return {
                "success": False,
                "error": f"JSON 解析失败: {str(e)}"
            }
        
        # 提取接口信息
        interfaces = []
        entries = har.get("log", {}).get("entries", [])
        
        for entry in entries:
            request = entry.get("request", {})
            response = entry.get("response", {})
            
            url = request.get("url", "")
            
            # 过滤域名
            if filter_domain and filter_domain not in url:
                continue
            
            # 解析 URL
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(url)
            
            interface = {
                "name": f"{request.get('method', 'GET')}_{parsed.path.replace('/', '_')}",
                "path": parsed.path,
                "method": request.get("method", "GET"),
                "full_url": url,
                "base_url": f"{parsed.scheme}://{parsed.netloc}",
                "parameters": [],
                "headers": [],
                "request_body": None,
                "response": {
                    "status": response.get("status"),
                    "status_text": response.get("statusText"),
                    "content_type": response.get("content", {}).get("mimeType")
                }
            }
            
            # 提取查询参数
            query_params = parse_qs(parsed.query)
            for name, values in query_params.items():
                interface["parameters"].append({
                    "name": name,
                    "in": "query",
                    "value": values[0] if len(values) == 1 else values
                })
            
            # 提取请求头
            for header in request.get("headers", []):
                interface["headers"].append({
                    "name": header.get("name"),
                    "value": header.get("value")
                })
            
            # 提取请求体
            post_data = request.get("postData")
            if post_data:
                interface["request_body"] = {
                    "mime_type": post_data.get("mimeType"),
                    "text": post_data.get("text"),
                    "params": post_data.get("params", [])
                }
            
            interfaces.append(interface)
        
        # 保存解析结果
        result = {
            "task_id": task_id,
            "total_entries": len(entries),
            "filtered_count": len(interfaces),
            "interfaces": interfaces
        }
        
        # 存储到文件系统
        storage_path = self.storage.save_interfaces(task_id, interfaces)
        
        self.logger.info(
            f"HAR 文件解析完成 | "
            f"任务ID: {task_id} | "
            f"总条目: {len(entries)} | "
            f"提取接口: {len(interfaces)}",
            task_id=task_id,
            interface_count=len(interfaces)
        )
        
        return {
            "success": True,
            "result": result,
            "storage_path": str(storage_path)
        }
    
    def _get_interfaces(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取已解析的接口列表
        
        Args:
            arguments: 工具参数
            
        Returns:
            接口列表
        """
        task_id = arguments["task_id"]
        
        try:
            interfaces = self.storage.load_interfaces(task_id)
            return {
                "success": True,
                "task_id": task_id,
                "interface_count": len(interfaces),
                "interfaces": interfaces
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取接口列表失败: {str(e)}"
            }
    
    def _parse_word(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析Word文档
        
        Args:
            arguments: 工具参数
            
        Returns:
            解析结果
        """
        task_id = arguments["task_id"]
        file_path = arguments["file_path"]
        extract_mode = arguments.get("extract_mode", "structured")
        
        self.logger.info(
            f"开始解析Word文档 | 任务ID: {task_id} | 文件: {file_path} | 模式: {extract_mode}",
            task_id=task_id,
            file_path=file_path,
            extract_mode=extract_mode
        )
        
        try:
            # 导入WordDocumentParser
            from .word_parser import WordDocumentParser
            
            parser = WordDocumentParser()
            
            # 验证文件
            if not parser.validate_file(file_path):
                return {
                    "success": False,
                    "error": "无效的Word文档文件，请确保文件格式为.docx"
                }
            
            # 获取文档信息
            doc_info = parser.get_document_info(file_path)
            
            # 根据提取模式处理
            if extract_mode == "text":
                content = parser.extract_text(file_path)
                content_type = "text"
            elif extract_mode == "structured":
                content = parser.extract_structured_content(file_path)
                content_type = "structured"
            else:  # tables
                content = parser.extract_tables(file_path)
                content_type = "tables"
            
            # 根据用户偏好添加详细日志
            if content_type == "text":
                content_preview = content[:200] if len(content) > 200 else content
                self.logger.info(
                    f"Word文本提取完成 | 任务ID: {task_id} | 长度: {len(content)} | 预览: {content_preview}...",
                    task_id=task_id,
                    content_length=len(content)
                )
            elif content_type == "structured":
                paragraphs = content.get('paragraphs', [])
                tables = content.get('tables', [])
                headings = content.get('headings', [])
                
                self.logger.info(
                    f"Word结构化内容提取完成 | 任务ID: {task_id} | 段落: {len(paragraphs)} | 表格: {len(tables)} | 标题: {len(headings)}",
                    task_id=task_id,
                    paragraph_count=len(paragraphs),
                    table_count=len(tables),
                    heading_count=len(headings)
                )
                
                # 打印标题预览
                if headings:
                    heading_preview = [h.get('text', '') for h in headings[:5]]  # 提取文本
                    self.logger.info(
                        f"Word标题预览 | 任务ID: {task_id} | 标题: {heading_preview}",
                        task_id=task_id
                    )
                
                # 打印段落预览（前300字符）
                if paragraphs:
                    try:
                        # 安全提取文本
                        text_parts = []
                        for p in paragraphs[:5]:  # 前5个段落
                            if isinstance(p, dict):
                                text_parts.append(p.get('text', ''))
                            elif isinstance(p, str):
                                text_parts.append(p)
                        
                        all_text = ' '.join(text_parts)
                        text_preview = all_text[:300] if len(all_text) > 300 else all_text
                        
                        self.logger.info(
                            f"Word段落预览 | 任务ID: {task_id} | 内容: {text_preview}",
                            task_id=task_id
                        )
                    except Exception as preview_error:
                        self.logger.warning(
                            f"Word段落预览失败 | 任务ID: {task_id} | 错误: {str(preview_error)}",
                            task_id=task_id
                        )
            else:  # tables
                self.logger.info(
                    f"Word表格提取完成 | 任务ID: {task_id} | 表格数: {len(content)}",
                    task_id=task_id,
                    table_count=len(content)
                )
            
            # 保存提取结果到storage
            import json
            from pathlib import Path
            
            storage_data = {
                "task_id": task_id,
                "file_path": file_path,
                "extract_mode": extract_mode,
                "content_type": content_type,
                "content": content,
                "doc_info": doc_info
            }
            
            # 获取任务目录
            task_dir = self.storage.get_task_directory(task_id)
            if not task_dir:
                task_dir = self.storage.create_task_directory(task_id)
            
            # 保存为JSON文件
            storage_path = Path(task_dir) / "documents" / "word_content.json"
            storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(storage_path, 'w', encoding='utf-8') as f:
                json.dump(storage_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(
                f"Word文档解析成功 | 任务ID: {task_id} | 存储路径: {storage_path}",
                task_id=task_id,
                storage_path=str(storage_path)
            )
            
            return {
                "success": True,
                "task_id": task_id,
                "extract_mode": extract_mode,
                "content_type": content_type,
                "content": content,
                "doc_info": doc_info,
                "storage_path": str(storage_path),
                "message": f"Word文档解析成功，提取模式: {extract_mode}"
            }
        
        except Exception as e:
            self.logger.error(
                f"Word文档解析失败 | 任务ID: {task_id} | 错误: {str(e)}",
                task_id=task_id,
                error=str(e),
                exc_info=True
            )
            return {
                "success": False,
                "error": f"Word文档解析失败: {str(e)}"
            }


def main():
    """独立运行时的入口点"""
    parser = DocumentParser(
        config={},
        logger=None,  # 使用默认 logger
        database=None,
        storage=None
    )
    parser.run()


if __name__ == "__main__":
    main()
