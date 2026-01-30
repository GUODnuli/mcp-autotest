# -*- coding: utf-8 -*-
"""
ChatAgent 入口文件

作为子进程被 Node.js Server 启动，执行 ReActAgent 并通过 Hook 回传消息。
迁移自 backend/agent/main.py，更新路径以适配新的目录结构。
"""
import asyncio
import socket
import sys
from datetime import datetime
from pathlib import Path

# Force IPv4 to avoid connection issues with Clash TUN Fake IP mode
_original_getaddrinfo = socket.getaddrinfo

def _ipv4_only_getaddrinfo(*args, **kwargs):
    results = _original_getaddrinfo(*args, **kwargs)
    ipv4 = [r for r in results if r[0] == socket.AF_INET]
    return ipv4 if ipv4 else results

socket.getaddrinfo = _ipv4_only_getaddrinfo

# 确保项目根目录和 agent 目录都在 Python 路径中
project_root = Path(__file__).parent.parent
agent_dir = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
if str(agent_dir) not in sys.path:
    sys.path.insert(0, str(agent_dir))

from agentscope.plan import PlanNotebook
import json5
from agentscope.agent import ReActAgent
from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from agentscope.tool import (
    Toolkit,
    execute_python_code
)
from tool.utils import (
    list_uploaded_files,
    safe_view_text_file,
    safe_write_text_file
)
from tool.doc_parser import (
    read_document,
    extract_api_spec,
    validate_api_spec
)
from tool.case_generator import (
    generate_positive_cases,
    generate_negative_cases,
    generate_security_cases
)
from tool.test_executor import (
    execute_api_test,
    validate_response,
    capture_metrics
)
from tool.report_tools import (
    generate_test_report,
    diagnose_failures,
    suggest_improvements
)
from tool_registry import setup_toolkit
from args import get_args
from model import get_model, get_formatter
from hook import AgentHooks, studio_pre_print_hook, studio_post_reply_hook


def _load_system_prompt() -> str:
    """加载系统提示词"""
    # 从项目根目录下的 prompts/ 加载
    prompt_path = project_root / "prompts" / "chat_default.md"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")

    # 默认提示词
    return """You are an AI assistant for the MCP API Testing Agent system.

# Core Objectives
- Help users understand and utilize the API testing features
- Answer questions about API testing, test case generation, and execution
- Provide testing best practices and professional recommendations
- Explain test reports and results in detail

# Critical Principles (MUST FOLLOW)
1. **Safety First**: Before executing any operation, ensure its safety
   - Do not execute dangerous operations that may damage data or systems
   - For file modification, deletion and other operations, confirm user intent first
   - Pay attention to privacy and security when dealing with sensitive information
2. **Tool-Driven Capabilities**: You have ReAct capabilities and can invoke MCP tools (document parsing, test generation, execution, etc.)
   - **NEVER claim inability to access files**: When users mention uploaded files or need specific operations, you MUST attempt to call relevant tools (e.g., external MCP tools from connected servers)
   - Always try tool invocation first before claiming limitations
3. **No Assumptions**: All information must come from users or tool results

# Workflow Process
1. Analyze user request and formulate a plan
2. Execute the plan step by step

# Response Guidelines
- Use friendly and professional tone
- Be concise and focused on user's specific context
- Avoid repeating material verbatim; summarize in your own words
- When user intent is unclear, proactively ask clarifying questions
- Clearly distinguish between "generating code" and "executing code" requests

# About This System
This is an MCP-based intelligent API testing system that supports:
- Multi-format document parsing (OpenAPI/Swagger, Postman, HAR, Word)
- Automated test case generation
- Test execution and result analysis
- Intelligent test planning and strategy recommendations

# File Access Protocol
When the user mentions uploaded files:
1. Extract user_id and conversation_id from the [SYSTEM CONTEXT] block in your input
2. Call list_uploaded_files(user_id, conversation_id) to get the correct file paths
3. Use the returned paths with safe_view_text_file

# Tool Management Protocol

- You have the capability to dynamically manage tools and can activate required tool groups via `reset_equipped_tools`.
- When handling uploaded files:
  1. Call `reset_equipped_tools({"api_test_tools": true})`
  2. Wait for the returned tool usage instructions
  3. Use `list_uploaded_files` and `safe_view_text_file` according to the instructions
- Immediately deactivate the tool group after completion: `reset_equipped_tools({"api_test_tools": false})`"""

async def main():
    """主入口函数"""
    args = get_args()

    print("=" * 60)
    print("ChatAgent 启动")
    print(f"会话 ID: {args.conversation_id}")
    print(f"回复 ID: {args.reply_id}")
    print(f"Server URL: {args.studio_url}")
    print("=" * 60)

    # 配置 Hook
    AgentHooks.url = args.studio_url
    AgentHooks.reply_id = args.reply_id

    # 注册类级 Hook
    ReActAgent.register_class_hook(
        "pre_print",
        "studio_pre_print_hook",
        studio_pre_print_hook
    )
    ReActAgent.register_class_hook(
        "post_reply",
        "studio_post_reply_hook",
        studio_post_reply_hook
    )

    # 初始化工具集
    toolkit = Toolkit()

    # 准备基础工具
    basic_tools = {
        'safe_write_text_file': safe_write_text_file,
        'safe_view_text_file': safe_view_text_file
    }

    # 准备 API 测试工具模块
    tool_modules = {
        'doc_parser': {
            'read_document': read_document,
            'extract_api_spec': extract_api_spec,
            'validate_api_spec': validate_api_spec
        },
        'case_generator': {
            'generate_positive_cases': generate_positive_cases,
            'generate_negative_cases': generate_negative_cases,
            'generate_security_cases': generate_security_cases
        },
        'test_executor': {
            'execute_api_test': execute_api_test,
            'validate_response': validate_response,
            'capture_metrics': capture_metrics
        },
        'report_tools': {
            'generate_test_report': generate_test_report,
            'diagnose_failures': diagnose_failures,
            'suggest_improvements': suggest_improvements
        }
    }

    # 一键配置所有工具和工具组
    toolkit = setup_toolkit(toolkit, tool_modules, basic_tools)

    # 获取模型
    model = get_model(
        args.llmProvider,
        args.modelName,
        args.apiKey,
        args.clientKwargs,
        args.generateKwargs
    )
    formatter = get_formatter(args.llmProvider)

    # 加载系统提示词
    system_prompt = _load_system_prompt()
    system_prompt += f"\n\n# 当前时间\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    # 加载自定义plan to hint
    from plan import (
        plan_to_hint,
        api_test_plan_to_hint
    )
    plan_to_hint = plan_to_hint.CustomPlanToHint()
    api_test_plan_to_hint = api_test_plan_to_hint.ApiTestPlanToHint()

    # 创建 ReActAgent
    agent = ReActAgent(
        name="ChatAgent",
        sys_prompt=system_prompt,
        model=model,
        formatter=formatter,
        toolkit=toolkit,
        memory=InMemoryMemory(),
        max_iters=50,
        plan_notebook=PlanNotebook(max_subtasks=50, plan_to_hint=plan_to_hint),
        enable_meta_tool=True
    )

    print("[OK] Agent 初始化完成")

    try:
        # 解析用户查询
        if args.query_from_stdin:
            # 从 stdin 读取 query
            query_str = sys.stdin.readline().strip()
            print(f"[INFO] 从 stdin 读取到: {query_str[:100]}...")
            query = json5.loads(query_str)
        else:
            # 从命令行参数读取
            query = json5.loads(args.query)

        print(f"[INFO] 用户查询: {str(query)[:100]}...")

        # 执行 Agent
        await agent(Msg("user", query, "user"))

    except Exception as e:
        print(f"[ERROR] Agent 执行失败: {e}")
        import traceback
        traceback.print_exc()

    print("=" * 60)
    print("ChatAgent 执行完毕")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(main())
