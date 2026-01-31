# -*- coding: utf-8 -*-
"""
MCP Server 生命周期管理

负责从配置加载 MCP Server，建立连接并在退出时清理。
使用 AgentScope 的 StdIOStatefulClient API。
"""
import logging
from typing import Dict

logger = logging.getLogger(__name__)


async def load_mcp_servers(mcp_config: dict) -> Dict[str, object]:
    """
    根据配置加载并连接 MCP Server。

    Args:
        mcp_config: mcpServers 配置字典，每个 key 为 server 名称，
                    value 包含 command, args, env, enabled 等字段。

    Returns:
        已连接的 MCP client 字典 {name: StdIOStatefulClient}。
        连接失败的 server 会被跳过（记录警告日志）。
    """
    from agentscope.mcp import StdIOStatefulClient

    clients: Dict[str, object] = {}

    for name, server_cfg in mcp_config.items():
        if not server_cfg.get("enabled", True):
            logger.info("MCP server '%s' is disabled, skipping", name)
            continue

        command = server_cfg.get("command", "")
        args = server_cfg.get("args", [])
        env = server_cfg.get("env", {})

        if not command:
            logger.warning("MCP server '%s' has no command, skipping", name)
            continue

        try:
            client = StdIOStatefulClient(
                name=name,
                command=command,
                args=args,
                env=env if env else None,
            )
            await client.connect()
            clients[name] = client
            logger.info("MCP server '%s' connected successfully", name)
        except Exception as exc:
            logger.warning("Failed to connect MCP server '%s': %s", name, exc)

    return clients


async def close_mcp_servers(clients: Dict[str, object]) -> None:
    """
    关闭所有 MCP Server 连接（LIFO 顺序）。

    Args:
        clients: load_mcp_servers 返回的 client 字典。
    """
    for name in reversed(list(clients.keys())):
        try:
            client = clients[name]
            if hasattr(client, "close"):
                await client.close()
            elif hasattr(client, "disconnect"):
                await client.disconnect()
            logger.info("MCP server '%s' closed", name)
        except Exception as exc:
            logger.warning("Error closing MCP server '%s': %s", name, exc)
