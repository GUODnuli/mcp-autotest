# -*- coding: utf-8 -*-
"""
工具注册编排模块

异步编排器，将内置工具注册、工具组注册、MCP 加载、技能加载统一协调。
支持从 skills/*/tools/ 目录动态加载域工具。
"""
import importlib.util
import json
import logging
import re
from pathlib import Path
from typing import Callable, Dict, List, Tuple, Any, get_type_hints

import yaml
from agentscope.tool import Toolkit, ToolResponse

from tool_groups import ToolGroupDefinition, get_builtin_tool_groups
from settings_loader import load_settings
from mcp_loader import load_mcp_servers, close_mcp_servers

logger = logging.getLogger(__name__)

# Module-level storage for tool display settings (accessible by frontend)
_tool_display_settings: Dict[str, Any] = {
    "names": {},
    "categories": {},
    "skills": {}  # Per-skill settings keyed by skill name
}


def get_tool_display_settings() -> Dict[str, Any]:
    """
    Get merged tool display settings for frontend.

    Returns a dictionary containing:
    - names: Tool name to display name mapping (merged from all sources)
    - categories: Tool categories from global settings
    - skills: Per-skill display settings keyed by skill name

    Example:
        {
            "names": {
                "execute_shell": "执行命令",
                "extract_api_spec": "提取接口规范",
                ...
            },
            "categories": {
                "base": {"displayName": "基础工具", "tools": [...]},
                ...
            },
            "skills": {
                "api_testing": {
                    "names": {...},
                    "categories": {...}
                }
            }
        }
    """
    return _tool_display_settings.copy()


def _load_skill_settings(skill_dir: Path) -> Dict[str, Any]:
    """
    Load skill-level settings from settings.json.

    Args:
        skill_dir: Path to the skill directory

    Returns:
        Dictionary of skill settings or empty dict if not found
    """
    settings_path = skill_dir / "settings.json"
    if not settings_path.exists():
        return {}

    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Failed to load skill settings from %s: %s", settings_path, exc)
        return {}


def _merge_tool_display_settings(global_settings: Dict[str, Any], skill_name: str, skill_settings: Dict[str, Any]) -> None:
    """
    Merge skill-level tool display settings into global storage.

    Args:
        global_settings: Global settings from .testagent/settings.json
        skill_name: Name of the skill
        skill_settings: Skill-level settings from skill/settings.json
    """
    global _tool_display_settings

    # Initialize from global settings if not done
    global_tool_display = global_settings.get("toolDisplay", {})
    if not _tool_display_settings["names"]:
        _tool_display_settings["names"] = global_tool_display.get("names", {}).copy()
        _tool_display_settings["categories"] = global_tool_display.get("categories", {}).copy()

    # Store skill-specific settings
    skill_tool_display = skill_settings.get("toolDisplay", {})
    if skill_tool_display:
        _tool_display_settings["skills"][skill_name] = skill_tool_display

        # Merge skill tool names into global names for easy lookup
        skill_names = skill_tool_display.get("names", {})
        _tool_display_settings["names"].update(skill_names)


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


def _ensure_tool_group(toolkit: Toolkit, group_name: str, display_name: str = "") -> None:
    """确保工具组存在，不存在则创建"""
    try:
        toolkit.create_tool_group(
            group_name=group_name,
            description=display_name or group_name,
        )
        logger.info("Created tool group '%s' for MCP server", group_name)
    except Exception:
        # 组已存在，忽略
        pass


async def _register_mcp_tools(toolkit: Toolkit, mcp_clients: Dict[str, object], mcp_config: dict) -> None:
    """将 MCP client 注册到 toolkit"""
    for name, client in mcp_clients.items():
        server_cfg = mcp_config.get(name, {})
        group_name = server_cfg.get("group", name)
        display_name = server_cfg.get("displayName", group_name)
        _ensure_tool_group(toolkit, group_name, display_name)
        try:
            await toolkit.register_mcp_client(
                client,
                group_name=group_name,
                namesake_strategy="skip",
            )
            logger.info("Registered MCP client '%s' to group '%s'", name, group_name)
        except Exception as exc:
            logger.warning("Failed to register MCP client '%s': %s", name, exc)


def _load_skill_tools(skill_dir: Path, expected_skills_parent: Path | None = None) -> List[Callable]:
    """
    Dynamically load tool functions from a skill's tools/ directory.

    Discovers Python modules in the tools/ subdirectory and extracts
    functions that return ToolResponse (identified by type hints).

    Security: Only loads skills from within the expected .testagent/skills/ directory.

    Args:
        skill_dir: Path to the skill directory containing SKILL.md
        expected_skills_parent: Expected parent directory for skills validation

    Returns:
        List of callable tool functions
    """
    # Security: Validate skill_dir is within expected boundaries
    if expected_skills_parent is not None:
        try:
            skill_dir.resolve().relative_to(expected_skills_parent.resolve())
        except ValueError:
            logger.warning("Security: Skill directory outside expected path: %s", skill_dir)
            return []

    tools_dir = skill_dir / "tools"
    if not tools_dir.exists():
        return []

    discovered = []

    for py_file in tools_dir.glob("*.py"):
        if py_file.name.startswith("_"):
            continue

        try:
            # Create a unique module name to avoid conflicts
            module_name = f"skill_tools_{skill_dir.name}_{py_file.stem}"

            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                continue

            module = importlib.util.module_from_spec(spec)
            # Register module in sys.modules before execution
            import sys
            sys.modules[module_name] = module
            try:
                spec.loader.exec_module(module)
            except Exception:
                del sys.modules[module_name]  # Cleanup on failure
                raise

            # Discover tool functions by checking return type annotation
            for name in dir(module):
                if name.startswith("_"):
                    continue

                obj = getattr(module, name)
                if not callable(obj):
                    continue

                # Check if function returns ToolResponse
                try:
                    hints = get_type_hints(obj)
                    return_type = hints.get("return")
                    if return_type is ToolResponse:
                        discovered.append(obj)
                        logger.debug("Discovered tool function: %s.%s", py_file.stem, name)
                except Exception:
                    # If we can't get type hints, skip this function
                    continue

        except Exception as exc:
            logger.warning("Failed to load tools from %s: %s", py_file, exc)

    return discovered


def _parse_skill_metadata(skill_path: Path) -> Dict[str, Any]:
    """
    Parse SKILL.md frontmatter for skill metadata.

    Args:
        skill_path: Path to SKILL.md file

    Returns:
        Dictionary of skill metadata (name, description, tools_dir, etc.)
    """
    try:
        content = skill_path.read_text(encoding="utf-8")

        # Extract YAML frontmatter between --- markers
        match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
        if not match:
            return {}

        frontmatter = match.group(1)
        return yaml.safe_load(frontmatter) or {}

    except Exception as exc:
        logger.warning("Failed to parse skill metadata from %s: %s", skill_path, exc)
        return {}


def _register_skills(toolkit: Toolkit, skills_dir: Path, global_settings: Dict[str, Any]) -> None:
    """
    从 .testagent/skills/ 加载并注册技能及其工具。

    For each skill:
    1. Register the skill metadata (SKILL.md) via register_agent_skill
    2. If tools_dir is specified, dynamically load tools and register as a tool group
    3. Load skill-level settings.json and merge into global tool display settings

    Args:
        toolkit: AgentScope Toolkit instance
        skills_dir: Path to .testagent/skills/ directory
        global_settings: Global settings from .testagent/settings.json
    """
    if not skills_dir.exists():
        return

    for skill_path in skills_dir.glob("*/SKILL.md"):
        skill_dir = skill_path.parent
        skill_name = skill_dir.name

        try:
            # Register skill metadata
            toolkit.register_agent_skill(str(skill_dir))
            logger.info("Registered skill from %s", skill_name)

            # Parse skill metadata for tools_dir
            metadata = _parse_skill_metadata(skill_path)
            tools_dir_name = metadata.get("tools_dir")

            # Load and merge skill-level settings
            skill_settings = _load_skill_settings(skill_dir)
            if skill_settings:
                _merge_tool_display_settings(global_settings, skill_name, skill_settings)
                logger.debug("Loaded settings for skill '%s'", skill_name)

            if tools_dir_name:
                # Dynamically load tools from the skill's tools directory
                # Security: Pass expected_skills_parent for path validation
                tools = _load_skill_tools(skill_dir, expected_skills_parent=skills_dir)

                if tools:
                    # Create tool group for this skill
                    group_name = f"{skill_name.replace('-', '_')}_tools"
                    description = metadata.get("description", f"Tools for {skill_name} skill")

                    # Ensure group exists
                    _ensure_tool_group(toolkit, group_name, description)

                    # Register each tool function (skip duplicates)
                    for tool_func in tools:
                        try:
                            toolkit.register_tool_function(tool_func, group_name=group_name)
                            logger.debug("Registered skill tool: %s -> %s", tool_func.__name__, group_name)
                        except Exception as exc:
                            # Check if it's a duplicate registration error
                            if "already registered" in str(exc).lower():
                                logger.info("Skipped duplicate tool '%s' (already registered)", tool_func.__name__)
                            else:
                                logger.warning("Failed to register tool %s: %s", tool_func.__name__, exc)

                    logger.info("Loaded %d tools from skill '%s'", len(tools), skill_name)

        except Exception as exc:
            logger.warning("Failed to register skill '%s': %s", skill_name, exc)


async def setup_toolkit(
    toolkit: Toolkit,
    tool_modules: dict | None = None,
    basic_tools: dict | None = None,
    settings_path: str | None = None,
) -> Tuple[Toolkit, Dict[str, object]]:
    """
    一键配置工具集（MCP + 技能 + 动态加载的域工具）。

    Base tools should be registered directly before calling this function.
    Domain tools are now loaded dynamically from skills/*/tools/.

    Args:
        toolkit: AgentScope 工具集实例
        tool_modules: [DEPRECATED] 工具模块字典，不再使用
        basic_tools: [DEPRECATED] 基础工具字典，不再使用
        settings_path: .testagent/settings.json 路径（可选）

    Returns:
        (toolkit, mcp_clients) 元组，mcp_clients 用于生命周期管理

    Side effects:
        Updates module-level _tool_display_settings which can be retrieved via
        get_tool_display_settings() for frontend tool name display.
    """
    global _tool_display_settings

    # Legacy: 注册基础工具（deprecated, base tools should be registered in main.py）
    if basic_tools:
        _register_basic_tools(toolkit, basic_tools)

    # Legacy: 注册内置工具组（deprecated, domain tools now loaded from skills）
    if tool_modules:
        builtin_groups = get_builtin_tool_groups(tool_modules)
        _register_tool_groups(toolkit, builtin_groups)

    # 加载配置
    settings = load_settings(settings_path)

    # Initialize global tool display settings from config
    global_tool_display = settings.get("toolDisplay", {})
    _tool_display_settings["names"] = global_tool_display.get("names", {}).copy()
    _tool_display_settings["categories"] = global_tool_display.get("categories", {}).copy()
    _tool_display_settings["skills"] = {}

    # 加载并注册 MCP Server
    mcp_config = settings.get("mcpServers", {})
    mcp_clients = await load_mcp_servers(mcp_config)
    await _register_mcp_tools(toolkit, mcp_clients, mcp_config)

    # 加载技能（包括动态加载域工具和技能级别设置）
    if settings_path:
        config_dir = Path(settings_path).parent
    else:
        config_dir = Path(__file__).parent.parent / ".testagent"
    _register_skills(toolkit, config_dir / "skills", settings)

    logger.info("Tool display settings loaded: %d tool names, %d skills",
                len(_tool_display_settings["names"]),
                len(_tool_display_settings["skills"]))

    return toolkit, mcp_clients
