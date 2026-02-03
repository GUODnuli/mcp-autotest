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
from agentscope.tool import Toolkit

# Base tools (always available, workspace-scoped)
from tool.base import (
    ToolConfig,
    execute_shell,
    read_file,
    write_file,
    edit_file,
    glob_files,
    grep_files,
    web_fetch,
)

# Legacy utilities (kept for backward compatibility during migration)
from tool.utils import list_uploaded_files
from tool_registry import setup_toolkit
from mcp_loader import close_mcp_servers
from args import get_args
from model import get_model, get_formatter
from hook import AgentHooks, studio_pre_print_hook, studio_post_reply_hook


def _load_system_prompt() -> str:
    """加载基础系统提示词（skill 由 Toolkit.register_agent_skill 管理）"""
    prompts_dir = project_root / "prompts"

    base_path = prompts_dir / "system_prompt.md"
    if base_path.exists():
        return base_path.read_text(encoding="utf-8")

    return "You are a TestAgent assistant, an AI agent that helps users with software testing and quality assurance tasks."

async def main():
    """主入口函数"""
    args = get_args()

    print("=" * 60)
    print("ChatAgent 启动")
    print(f"会话 ID: {args.conversation_id}")
    print(f"回复 ID: {args.reply_id}")
    print(f"Server URL: {args.studio_url}")
    print(f"工作区: {args.workspace}")
    print(f"写权限: {args.writePermission}")
    print("=" * 60)

    # 初始化 ToolConfig（所有 base tools 依赖此配置）
    ToolConfig.init(workspace=args.workspace, write_permission=args.writePermission)

    # 添加 storage 子目录为允许访问的路径
    # - storage/chat: 用于读取用户上传的文件 (list_uploaded_files 返回的路径相对于此)
    # - storage/cache: 用于写入生成的文件
    storage_chat_dir = project_root / "storage" / "chat"
    storage_cache_dir = project_root / "storage" / "cache"
    if storage_chat_dir.exists():
        ToolConfig.get().add_allowed_path(storage_chat_dir)
    if storage_cache_dir.exists():
        ToolConfig.get().add_allowed_path(storage_cache_dir)
    elif args.writePermission:
        # 如果 cache 目录不存在但有写权限，创建它
        storage_cache_dir.mkdir(parents=True, exist_ok=True)
        ToolConfig.get().add_allowed_path(storage_cache_dir)

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

    # 注册 base tools（always available, no tool group）
    base_tools = [
        execute_shell,
        read_file,
        write_file,
        edit_file,
        glob_files,
        grep_files,
        web_fetch,
        list_uploaded_files,  # Legacy utility kept for conversation file access
    ]
    for tool_func in base_tools:
        toolkit.register_tool_function(tool_func)

    # 一键配置 MCP 和 skill tools（domain tools loaded from skills/*/tools/）
    settings_path = str(project_root / ".testagent" / "settings.json")
    toolkit, mcp_clients = await setup_toolkit(toolkit, settings_path=settings_path)

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

    # 加载自定义 plan to hint
    from plan.plan_to_hint import CustomPlanToHint
    plan_to_hint = CustomPlanToHint()

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
    finally:
        # 清理 MCP 连接
        await close_mcp_servers(mcp_clients)

    print("=" * 60)
    print("ChatAgent 执行完毕")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(main())
