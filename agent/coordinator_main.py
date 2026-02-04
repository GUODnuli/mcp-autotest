# -*- coding: utf-8 -*-
"""
Coordinator Agent 入口文件

支持两种模式：
1. 直接模式 (direct): 使用单个 ReActAgent 处理请求（现有行为）
2. 协调模式 (coordinator): 使用 Coordinator 分解任务并调度多个 Worker

通过命令行参数 --mode 切换，默认为 direct 模式保持向后兼容。
"""
import asyncio
import socket
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

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

import json5
from agentscope.agent import ReActAgent
from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from agentscope.plan import PlanNotebook
from agentscope.tool import Toolkit

# Base tools
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
from tool.utils import list_uploaded_files
from tool_registry import setup_toolkit
from mcp_loader import close_mcp_servers
from args import get_args
from model import get_model, get_formatter
from hook import AgentHooks, studio_pre_print_hook, studio_post_reply_hook

# Coordinator imports
from coordinator import Coordinator, CoordinatorConfig


def _load_system_prompt() -> str:
    """加载基础系统提示词"""
    prompts_dir = project_root / "prompts"
    base_path = prompts_dir / "system_prompt.md"
    if base_path.exists():
        return base_path.read_text(encoding="utf-8")
    return "You are a TestAgent assistant."


def _create_progress_callback(studio_url: str, reply_id: str):
    """创建 Coordinator 进度回调函数"""
    import httpx

    def callback(event_type: str, data: dict):
        """将 Coordinator 事件推送到前端"""
        if not studio_url or not reply_id:
            return

        # 转换为前端可理解的事件格式
        events = [{
            "type": "coordinator_event",
            "event_type": event_type,
            "data": data,
            "sequence": 0,
        }]

        payload = {
            "replyId": reply_id,
            "events": events,
        }

        try:
            with httpx.Client(timeout=5.0) as client:
                client.post(
                    f"{studio_url}/trpc/pushMessageToChatAgent",
                    json=payload,
                )
        except Exception as e:
            print(f"[Hook Warning] Failed to push coordinator event: {e}")

    return callback


async def run_direct_mode(args, toolkit: Toolkit, model, formatter):
    """直接模式：使用单个 ReActAgent"""
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

    print("[OK] Agent 初始化完成 (Direct Mode)")

    # 解析用户查询
    if args.query_from_stdin:
        query_str = sys.stdin.readline().strip()
        print(f"[INFO] 从 stdin 读取到: {query_str[:100]}...")
        query = json5.loads(query_str)
    else:
        query = json5.loads(args.query)

    print(f"[INFO] 用户查询: {str(query)[:100]}...")

    # 执行 Agent
    await agent(Msg("user", query, "user"))


async def run_coordinator_mode(args, toolkit: Toolkit, model):
    """协调模式：使用 Coordinator 分解任务并调度 Workers"""
    # 配置 Coordinator
    config = CoordinatorConfig(
        agents_dir=project_root / ".testagent" / "agents",
        skills_dir=project_root / ".testagent" / "skills",
        prompts_dir=project_root / "prompts" / "coordinator",
        max_phases=10,
        max_retries=3,
        timeout=1800,
        max_parallel_workers=5,
    )

    # 创建进度回调
    progress_callback = _create_progress_callback(args.studio_url, args.reply_id)

    # 创建 Coordinator
    coordinator = Coordinator(
        model=model,
        toolkit=toolkit,
        config=config,
        progress_callback=progress_callback,
    )

    # 初始化（加载 Workers 和 Skills）
    await coordinator.initialize()

    print("[OK] Coordinator 初始化完成 (Coordinator Mode)")

    # 解析用户查询
    if args.query_from_stdin:
        query_str = sys.stdin.readline().strip()
        print(f"[INFO] 从 stdin 读取到: {query_str[:100]}...")
        query = json5.loads(query_str)
    else:
        query = json5.loads(args.query)

    # 提取目标文本
    if isinstance(query, dict):
        objective = query.get("content", query.get("text", str(query)))
    else:
        objective = str(query)

    print(f"[INFO] 用户目标: {objective[:100]}...")

    # 执行 Coordinator
    result = await coordinator.execute(
        objective=objective,
        context={"workspace": args.workspace},
        session_id=args.conversation_id,
    )

    # 输出结果摘要
    print(f"[INFO] 执行结果: {result.get('status')}")
    if result.get("error"):
        print(f"[ERROR] {result['error']}")

    return result


async def main():
    """主入口函数"""
    args = get_args()

    # 检查模式参数（默认 direct）
    mode = getattr(args, 'mode', 'direct') or 'direct'

    print("=" * 60)
    print(f"ChatAgent 启动 (Mode: {mode})")
    print(f"会话 ID: {args.conversation_id}")
    print(f"回复 ID: {args.reply_id}")
    print(f"Server URL: {args.studio_url}")
    print(f"工作区: {args.workspace}")
    print(f"写权限: {args.writePermission}")
    print("=" * 60)

    # 初始化 ToolConfig
    ToolConfig.init(workspace=args.workspace, write_permission=args.writePermission)

    # 添加 storage 子目录为允许访问的路径
    storage_chat_dir = project_root / "storage" / "chat"
    storage_cache_dir = project_root / "storage" / "cache"
    if storage_chat_dir.exists():
        ToolConfig.get().add_allowed_path(storage_chat_dir)
    if storage_cache_dir.exists():
        ToolConfig.get().add_allowed_path(storage_cache_dir)
    elif args.writePermission:
        storage_cache_dir.mkdir(parents=True, exist_ok=True)
        ToolConfig.get().add_allowed_path(storage_cache_dir)

    # 配置 Hook
    AgentHooks.url = args.studio_url
    AgentHooks.reply_id = args.reply_id

    # 初始化工具集
    toolkit = Toolkit()

    # 注册 base tools
    base_tools = [
        execute_shell,
        read_file,
        write_file,
        edit_file,
        glob_files,
        grep_files,
        web_fetch,
        list_uploaded_files,
    ]
    for tool_func in base_tools:
        toolkit.register_tool_function(tool_func)

    # 配置 MCP 和 skill tools
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

    try:
        if mode == "coordinator":
            await run_coordinator_mode(args, toolkit, model)
        else:
            formatter = get_formatter(args.llmProvider)
            await run_direct_mode(args, toolkit, model, formatter)

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
