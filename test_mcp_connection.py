"""
测试 MCP 连接和工具注册

用于验证 AgentScope 的 MCP 客户端能否正常连接到 MCP Server 并注册工具。
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from agentscope.mcp import StdIOStatefulClient
from agentscope.tool import Toolkit


async def test_mcp_connection():
    """测试 MCP 连接"""
    print("=" * 60)
    print("开始测试 MCP 连接...")
    print("=" * 60)
    
    # 配置 MCP Server 启动命令 - 将命令和参数分开
    uvx_executable = r"C:\\Users\\62411\\.local\\bin\\uvx.exe"
    uvx_args = ["--python", "3.12", "awslabs.document-loader-mcp-server@latest"]
    
    # 不使用引号，直接拼接
    full_command = f"{uvx_executable} {' '.join(uvx_args)}"
    
    print(f"\n使用命令: {full_command}")
    
    try:
        # 1. 创建 MCP 客户端
        print("\n[步骤 1] 创建 MCP 客户端...")
        client = StdIOStatefulClient(
            name="document_loader",
            command=full_command  # 使用完整命令字符串
        )
        print("✓ MCP 客户端创建成功")
        
        # 2. 连接到 MCP Server
        print("\n[步骤 2] 连接到 MCP Server...")
        await client.connect()
        print("✓ MCP Server 连接成功")
        
        # 3. 列出可用工具
        print("\n[步骤 3] 获取可用工具列表...")
        tools = await client.list_tools()
        print(f"✓ 发现 {len(tools)} 个工具:")
        for i, tool in enumerate(tools, 1):
            print(f"  {i}. {tool.get('name')} - {tool.get('description', 'No description')}")
        
        # 4. 注册工具到 Toolkit
        print("\n[步骤 4] 注册工具到 Toolkit...")
        toolkit = Toolkit()
        await toolkit.register_mcp_client(client)
        
        # 获取已注册的工具列表
        registered_tools = toolkit.get_json_schemas()
        print(f"✓ 成功注册 {len(registered_tools)} 个工具到 Toolkit")
        
        # 5. 显示工具的 JSON Schema
        print("\n[步骤 5] 工具详细信息:")
        for i, tool_schema in enumerate(registered_tools, 1):
            tool_func = tool_schema.get("function", {})
            print(f"\n  工具 {i}: {tool_func.get('name')}")
            print(f"  描述: {tool_func.get('description')}")
            parameters = tool_func.get("parameters", {})
            props = parameters.get("properties", {})
            if props:
                print(f"  参数:")
                for param_name, param_info in props.items():
                    param_type = param_info.get("type", "unknown")
                    param_desc = param_info.get("description", "")
                    required = param_name in parameters.get("required", [])
                    req_str = "[必需]" if required else "[可选]"
                    print(f"    - {param_name} ({param_type}) {req_str}: {param_desc}")
        
        # 6. 关闭连接
        print("\n[步骤 6] 关闭连接...")
        await client.close()
        print("✓ 连接已关闭")
        
        print("\n" + "=" * 60)
        print("✓ 所有测试通过！")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_tool_call():
    """测试工具调用"""
    print("\n" + "=" * 60)
    print("测试工具调用功能...")
    print("=" * 60)
    
    # 配置 MCP Server 启动命令 - 将命令和参数分开
    uvx_executable = r"C:\Users\62411\.local\bin\uvx.exe"
    uvx_args = ["--python", "3.12", "awslabs.document-loader-mcp-server@latest"]
    full_command = f'"{uvx_executable}" {" ".join(uvx_args)}'
    
    try:
        # 创建并连接客户端
        print("\n[准备] 连接到 MCP Server...")
        client = StdIOStatefulClient(
            name="document_loader",
            command=full_command
        )
        await client.connect()
        print("✓ 连接成功")
        
        # 获取可调用函数对象
        print("\n[测试] 获取可调用函数...")
        tools = await client.list_tools()
        if not tools:
            print("✗ 没有可用的工具")
            return False
        
        first_tool = tools[0]
        tool_name = first_tool.get("name")
        print(f"✓ 测试工具: {tool_name}")
        
        # 获取可调用函数
        func = await client.get_callable_function(
            func_name=tool_name,
            wrap_tool_result=True
        )
        
        print(f"  函数名: {func.name}")
        print(f"  函数描述: {func.description}")
        
        # 注意：实际调用需要提供正确的参数，这里只测试函数获取
        print("✓ 可调用函数获取成功")
        
        # 关闭连接
        await client.close()
        print("\n✓ 工具调用测试完成")
        
        return True
        
    except Exception as e:
        print(f"\n✗ 工具调用测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("MCP 连接和工具注册测试")
    print("=" * 60)
    
    # 测试 1: 基本连接和工具注册
    test1_result = await test_mcp_connection()
    
    # 测试 2: 工具调用
    test2_result = await test_tool_call()
    
    # 总结
    print("\n" + "=" * 60)
    print("测试总结:")
    print("=" * 60)
    print(f"基本连接测试: {'✓ 通过' if test1_result else '✗ 失败'}")
    print(f"工具调用测试: {'✓ 通过' if test2_result else '✗ 失败'}")
    print("=" * 60)
    
    return test1_result and test2_result


if __name__ == "__main__":
    import platform
    
    # Windows 特殊处理
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
