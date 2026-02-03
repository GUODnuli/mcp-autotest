# -*- coding: utf-8 -*-
"""命令行参数解析"""
import json
from argparse import ArgumentParser, Namespace


def json_type(value: str) -> dict:
    """将 JSON 字符串解析为字典"""
    if not value or value == "":
        return {}
    try:
        result = json.loads(value)
        if not isinstance(result, dict):
            raise ValueError("JSON 必须是对象/字典类型")
        return result
    except json.JSONDecodeError as e:
        raise ValueError(f"无效的 JSON 字符串: {e}")


def get_args() -> Namespace:
    """获取命令行参数"""
    parser = ArgumentParser(description="ChatAgent 命令行参数")
    
    parser.add_argument(
        "--query",
        type=str,
        required=False,
        help="用户查询内容（JSON 格式）"
    )
    parser.add_argument(
        "--query-from-stdin",
        action="store_true",
        help="从 stdin 读取 query（避免 Windows 命令行参数问题）"
    )
    parser.add_argument(
        "--studio_url",
        type=str,
        required=True,
        help="Server URL（用于 HTTP 回传和 Socket 连接）"
    )
    parser.add_argument(
        "--conversation_id",
        type=str,
        required=True,
        help="会话 ID"
    )
    parser.add_argument(
        "--reply_id",
        type=str,
        required=True,
        help="回复 ID"
    )
    parser.add_argument(
        "--llmProvider",
        choices=["dashscope", "openai", "anthropic", "gemini", "ollama"],
        required=True,
        help="LLM 提供商"
    )
    parser.add_argument(
        "--modelName",
        type=str,
        required=True,
        help="模型名称"
    )
    parser.add_argument(
        "--apiKey",
        type=str,
        required=True,
        help="API Key"
    )
    parser.add_argument(
        "--writePermission",
        type=lambda x: x.lower() == 'true',
        default=False,
        help="是否有写权限"
    )
    parser.add_argument(
        "--workspace",
        type=str,
        required=False,
        default=".",
        help="工作区根目录（Agent 文件操作的沙箱根路径）"
    )
    parser.add_argument(
        "--clientKwargs",
        type=json_type,
        default={},
        help="LLM 客户端额外参数（JSON 字符串）"
    )
    parser.add_argument(
        "--generateKwargs",
        type=json_type,
        default={},
        help="LLM 生成额外参数（JSON 字符串）"
    )
    
    args = parser.parse_args()
    return args
