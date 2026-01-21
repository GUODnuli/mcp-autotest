"""
MCP 接口测试智能体应用 - 主入口

启动 Agent 服务和所有 MCP Servers。
"""

import asyncio
import sys
import platform
from pathlib import Path

# Windows 特殊处理：设置 ProactorEventLoop 以支持子进程
if platform.system() == 'Windows':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# 确保项目根目录在 Python 路径中
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from backend.common import (
    ConfigManager,
    Logger,
    Database,
    StorageManager,
    VectorDB,
    MemoryManager,
    get_config_manager,
    load_all_configs
)
from backend.service import AgentService


async def initialize_application():
    """初始化应用程序"""
    print("=" * 60)
    print("MCP 接口测试智能体应用")
    print("正在初始化...")
    print("=" * 60)
    
    # 1. 加载配置
    config_manager = get_config_manager()
    configs = load_all_configs()
    
    default_config = configs["default"]
    agent_config = configs["agent"]
    storage_config = configs["storage"]
    vectordb_config = configs["vectordb"]
    dify_config = configs["dify"]
    testengine_config = configs["testengine"]
    web_config = configs["web"]
    model_config = configs["model"]
    
    print("[OK] 配置加载完成")
    
    # 2. 初始化日志系统
    logger = Logger(
        log_level=default_config.log_level,
        log_file=default_config.log_file,
        enable_file=True
    )
    logger.info("应用程序启动", component="main")
    print("[OK] 日志系统初始化完成")
    
    # 3. 初始化数据库
    database = Database(
        database_path=storage_config.database_path
    )
    print("[OK] 数据库初始化完成")
    
    # 4. 初始化文件存储
    storage = StorageManager(
        root_path=storage_config.root_path
    )
    print("[OK] 文件存储初始化完成")
    
    # 5. 初始化向量数据库
    vectordb = VectorDB(
        config=vectordb_config.dict()
    )
    print("[OK] 向量数据库初始化完成")
    
    # 6. 初始化记忆管理器
    memory_manager = MemoryManager(
        working_memory_capacity=100,
        vectordb_config=vectordb_config.dict()
    )
    print("[OK] 记忆管理器初始化完成")
    
    # 6.5. 初始化 LLM 客户端（用于 Word 文档转接口）
    from backend.common.llm_client import get_llm_client
    try:
        llm_client = get_llm_client(dify_config.dict())
        print("[OK] LLM 客户端初始化完成")
        logger.info("LLM 客户端初始化成功", component="main")
    except Exception as e:
        llm_client = None
        print(f"[WARN] LLM 客户端初始化失败: {str(e)}")
        logger.warning(f"LLM 客户端初始化失败，Word 文档转接口功能不可用: {str(e)}", component="main")
    
    # 7. 初始化 AgentScope 有状态 MCP 客户端并连接
    from agentscope.mcp import StdIOStatefulClient
    
    mcp_clients = []
    mcp_servers_config = agent_config.mcp_servers
    
    for s_conf in mcp_servers_config:
        try:
            logger.info(f"[MCP] 正在初始化有状态 MCP 客户端: {s_conf.id}")
            
            # 如果配置了 args 字段，则将 command 和 args 合并
            if s_conf.args:
                # 合并 command 和 args 为完整命令
                full_command = f"{s_conf.command} {' '.join(s_conf.args)}"
                logger.info(f"[MCP] 使用合并命令: {full_command}")
            else:
                full_command = s_conf.command
                logger.info(f"[MCP] 使用配置命令: {full_command}")
            
            client = StdIOStatefulClient(
                name=s_conf.id,
                command=full_command
            )
            
            # 连接到 MCP Server
            logger.info(f"[MCP] 正在连接 MCP Server: {s_conf.id}")
            await client.connect()
            
            mcp_clients.append(client)
            print(f"[OK] MCP Server '{s_conf.id}' 连接成功")
            logger.info(f"[MCP] Server '{s_conf.id}' 连接成功")
            
        except Exception as e:
            print(f"[ERR] MCP Server '{s_conf.id}' 连接异常: {str(e)}")
            logger.error(f"MCP Server '{s_conf.id}' 连接失败: {str(e)}", exc_info=True)

    # 8. 初始化 Agent HTTP 服务
    agent_service = AgentService(
        logger=logger,
        database=database,
        mcp_clients=mcp_clients,
        storage=storage,
        config=web_config.dict(),
        dify_config=dify_config.dict(),
        model_config=model_config
    )
    print("[OK] Agent HTTP 服务初始化完成")
    
    print("=" * 60)
    print("应用程序初始化完成！")
    print(f"API 服务地址: http://{web_config.host}:{web_config.port}")
    print(f"API 文档地址: http://{web_config.host}:{web_config.port}/docs")
    print("=" * 60)
    
    return agent_service, web_config


def main():
    """主入口函数"""
    try:
        # 初始化应用
        agent_service, web_config = asyncio.run(initialize_application())
        
        # 启动服务
        agent_service.run(
            host=web_config.host,
            port=web_config.port
        )
    
    except KeyboardInterrupt:
        print("\n应用程序已停止")
    except Exception as e:
        print(f"\n应用程序启动失败: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
