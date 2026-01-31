# -*- coding: utf-8 -*-
"""
工具注册编排模块

异步编排器，将内置工具注册、工具组注册、MCP 加载、技能加载统一协调。
"""
import logging
from pathlib import Path
from typing import Dict, List, Tuple

from agentscope.tool import Toolkit

from tool_groups import ToolGroupDefinition, get_builtin_tool_groups
from settings_loader import load_settings
from mcp_loader import load_mcp_servers, close_mcp_servers

logger = logging.getLogger(__name__)


def _register_basic_tools(toolkit: Toolkit, basic_tools: dict) -> None:
    """注册基础工具（不分组）"""
    for tool_func in basic_tools.values():
        toolkit.register_tool_function(tool_func)


def _register_tool_groups(toolkit: Toolkit, tool_groups: List[ToolGroupDefinition]) -> None:
    """批量注册工具组"""
    for group_def in tool_groups:
        toolkit.create_tool_group(
            group_name=group_def.group_name,
            description=group_def.description,
            notes=group_def.notes,
        )
        for tool in group_def.tools:
            toolkit.register_tool_function(tool, group_name=group_def.group_name)


async def _register_mcp_tools(toolkit: Toolkit, mcp_clients: Dict[str, object], mcp_config: dict) -> None:
    """将 MCP client 注册到 toolkit"""
    for name, client in mcp_clients.items():
        group_name = mcp_config.get(name, {}).get("group", name)
        try:
            await toolkit.register_mcp_client(
                client,
                group_name=group_name,
                namesake_strategy="skip",
            )
            logger.info("Registered MCP client '%s' to group '%s'", name, group_name)
        except Exception as exc:
            logger.warning("Failed to register MCP client '%s': %s", name, exc)


def _register_skills(toolkit: Toolkit, skills_dir: Path) -> None:
    """从 .autotest/skills/ 加载并注册技能"""
    if not skills_dir.exists():
        return

    for skill_path in skills_dir.glob("*.md"):
        try:
            toolkit.register_agent_skill(str(skill_path))
            logger.info("Registered skill from %s", skill_path.name)
        except Exception as exc:
            logger.warning("Failed to register skill '%s': %s", skill_path.name, exc)


async def setup_toolkit(
    toolkit: Toolkit,
    tool_modules: dict,
    basic_tools: dict | None = None,
    settings_path: str | None = None,
) -> Tuple[Toolkit, Dict[str, object]]:
    """
    一键配置工具集（基础工具 + 工具组 + MCP + 技能）。

    Args:
        toolkit: AgentScope 工具集实例
        tool_modules: 工具模块字典
        basic_tools: 基础工具字典（可选）
        settings_path: .autotest/settings.json 路径（可选）

    Returns:
        (toolkit, mcp_clients) 元组，mcp_clients 用于生命周期管理
    """
    # 1. 注册基础工具
    if basic_tools:
        _register_basic_tools(toolkit, basic_tools)

    # 2. 注册内置工具组
    builtin_groups = get_builtin_tool_groups(tool_modules)
    _register_tool_groups(toolkit, builtin_groups)

    # 3. 加载配置
    settings = load_settings(settings_path)

    # 4. 加载并注册 MCP Server
    mcp_config = settings.get("mcpServers", {})
    mcp_clients = await load_mcp_servers(mcp_config)
    await _register_mcp_tools(toolkit, mcp_clients, mcp_config)

    # 5. 加载技能
    if settings_path:
        autotest_dir = Path(settings_path).parent
    else:
        autotest_dir = Path(__file__).parent.parent / ".autotest"
    _register_skills(toolkit, autotest_dir / "skills")

    return toolkit, mcp_clients
