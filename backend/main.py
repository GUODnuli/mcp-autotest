"""
MCP 接口测试智能体应用 - 主入口

启动 Agent 服务和所有 MCP Servers。
"""

import asyncio
import sys
from pathlib import Path

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
from backend.agent import (
    TaskManager,
    WorkflowOrchestrator,
    AgentService
)
from backend.mcp_servers.doc_parser import DocumentParser
from backend.mcp_servers.testcase_generator import TestCaseGenerator
from backend.mcp_servers.test_executor import TestExecutor
from backend.mcp_servers.report_analyzer import ReportAnalyzer


# 全局app实例，供热重载模式使用
app = None


def create_app():
    """创建并返回FastAPI应用实例（用于热重载）"""
    global app
    if app is None:
        # 在已存在的事件循环中执行异步初始化
        import asyncio
        try:
            # 尝试获取当前运行的事件循环
            loop = asyncio.get_running_loop()
            # 如果已有运行中的循环，使用同步初始化
            app = _sync_initialize_application()
        except RuntimeError:
            # 没有运行中的事件循环，使用asyncio.run
            _, _ = asyncio.run(initialize_application())
    return app


def _sync_initialize_application():
    """同步初始化应用（用于热重载模式）"""
    print("=" * 60)
    print("MCP 接口测试智能体应用（热重载模式）")
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
    
    print("[OK] 配置加载完成")
    
    # 2. 初始化日志系统
    logger = Logger(
        log_level=default_config.log_level,
        log_file=default_config.log_file,
        enable_file=True
    )
    logger.info("应用程序启动（热重载模式）", component="main")
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
    
    # 7. 初始化任务管理器
    task_manager = TaskManager(
        logger=logger,
        database=database,
        storage=storage
    )
    print("[OK] 任务管理器初始化完成")
    
    # 8. 初始化 MCP Servers
    doc_parser = DocumentParser(
        config={},
        logger=logger,
        database=database,
        storage=storage,
        llm_client=llm_client  # 注入 LLM 客户端
    )
    print("[OK] 文档解析 Server 初始化完成")
    
    testcase_generator = TestCaseGenerator(
        config=dify_config.dict(),
        logger=logger,
        database=database,
        storage=storage,
        memory_manager=memory_manager
    )
    print("[OK] 测试用例生成 Server 初始化完成")
    
    test_executor = TestExecutor(
        config=testengine_config.dict(),
        logger=logger,
        database=database,
        storage=storage
    )
    print("[OK] 测试执行 Server 初始化完成")
    
    # 初始化报告分析 Server
    report_analyzer = ReportAnalyzer(
        config=dify_config.dict(),
        logger=logger,
        database=database,
        storage=storage
    )
    print("[OK] 报告分析 Server 初始化完成")
    
    # 9. 初始化工作流编排器
    workflow_orchestrator = WorkflowOrchestrator(
        task_manager=task_manager,
        logger=logger,
        database=database,
        storage=storage,
        memory_manager=memory_manager
    )
    
    # 注册 MCP Servers
    workflow_orchestrator.register_mcp_server("doc_parser", doc_parser)
    workflow_orchestrator.register_mcp_server("testcase_generator", testcase_generator)
    workflow_orchestrator.register_mcp_server("test_executor", test_executor)
    workflow_orchestrator.register_mcp_server("report_analyzer", report_analyzer)
    
    print("[OK] 工作流编排器初始化完成")
    
    # 10. 初始化 Agent HTTP 服务
    agent_service = AgentService(
        task_manager=task_manager,
        workflow_orchestrator=workflow_orchestrator,
        logger=logger,
        config=web_config.dict()
    )
    print("[OK] Agent HTTP 服务初始化完成")
    
    print("=" * 60)
    print("应用程序初始化完成！")
    print(f"API 服务地址: http://{web_config.host}:{web_config.port}")
    print(f"API 文档地址: http://{web_config.host}:{web_config.port}/docs")
    print("=" * 60)
    
    return agent_service.app


async def initialize_application():
    """初始化应用程序"""
    global app  # 声明使用全局变量
    
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
    
    # 7. 初始化任务管理器
    task_manager = TaskManager(
        logger=logger,
        database=database,
        storage=storage
    )
    print("[OK] 任务管理器初始化完成")
    
    # 8. 初始化 MCP Servers
    doc_parser = DocumentParser(
        config={},
        logger=logger,
        database=database,
        storage=storage,
        llm_client=llm_client  # 注入 LLM 客户端
    )
    print("[OK] 文档解析 Server 初始化完成")
    
    testcase_generator = TestCaseGenerator(
        config=dify_config.dict(),
        logger=logger,
        database=database,
        storage=storage,
        memory_manager=memory_manager
    )
    print("[OK] 测试用例生成 Server 初始化完成")
    
    test_executor = TestExecutor(
        config=testengine_config.dict(),
        logger=logger,
        database=database,
        storage=storage
    )
    print("[OK] 测试执行 Server 初始化完成")
    
    # 初始化报告分析 Server
    report_analyzer = ReportAnalyzer(
        config=dify_config.dict(),
        logger=logger,
        database=database,
        storage=storage
    )
    print("[OK] 报告分析 Server 初始化完成")
    
    # 9. 初始化工作流编排器
    workflow_orchestrator = WorkflowOrchestrator(
        task_manager=task_manager,
        logger=logger,
        database=database,
        storage=storage,
        memory_manager=memory_manager
    )
    
    # 注册 MCP Servers
    workflow_orchestrator.register_mcp_server("doc_parser", doc_parser)
    workflow_orchestrator.register_mcp_server("testcase_generator", testcase_generator)
    workflow_orchestrator.register_mcp_server("test_executor", test_executor)
    workflow_orchestrator.register_mcp_server("report_analyzer", report_analyzer)
    
    print("[OK] 工作流编排器初始化完成")
    
    # 10. 初始化 Agent HTTP 服务
    agent_service = AgentService(
        task_manager=task_manager,
        workflow_orchestrator=workflow_orchestrator,
        logger=logger,
        config=web_config.dict()
    )
    print("[OK] Agent HTTP 服务初始化完成")
    
    # 保存全局app实例
    app = agent_service.app
    
    print("=" * 60)
    print("应用程序初始化完成！")
    print(f"API 服务地址: http://{web_config.host}:{web_config.port}")
    print(f"API 文档地址: http://{web_config.host}:{web_config.port}/docs")
    print("=" * 60)
    
    return agent_service, web_config


def main():
    """主入口函数"""
    import os
    
    # 检查环境变量确定是否启用热重载
    reload_mode = os.getenv("RELOAD", "false").lower() == "true"
    
    try:
        # 初始化应用
        agent_service, web_config = asyncio.run(initialize_application())
        
        # 启动服务
        agent_service.run(
            host=web_config.host,
            port=web_config.port,
            reload=reload_mode  # 传递热重载参数
        )
    
    except KeyboardInterrupt:
        print("\n应用程序已停止")
    except Exception as e:
        print(f"\n应用程序启动失败: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
