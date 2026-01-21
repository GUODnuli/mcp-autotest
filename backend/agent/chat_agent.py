"""
聊天 Agent 服务

基于 AgentScope ReActAgent 实现 User-Assistant 对话功能。
支持计划模式（PlanNotebook）和 MCP 工具集成。
"""

import json
import uuid
import time
import asyncio
from typing import Any, Dict, Generator, List, Optional, AsyncGenerator, Callable, Union
from datetime import datetime

from backend.common.logger import get_logger
from backend.common.database import Database
from backend.common.config import get_config_manager, ModelConfig

from agentscope.agent import ReActAgent
from agentscope.formatter import DashScopeChatFormatter, DashScopeMultiAgentFormatter
from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from agentscope.model import DashScopeChatModel
from agentscope.tool import (
    Toolkit,
    ToolResponse, 
    execute_python_code,
    execute_shell_command,
    write_text_file,
    insert_text_file,
    view_text_file,
)
from agentscope.mcp import StdIOStatefulClient
from agentscope.plan import PlanNotebook
from agentscope.pipeline import MsgHub
import os
from contextvars import ContextVar
from pathlib import Path
from backend.agent.plan.plan_to_hint import CustomPlanToHint

logger = get_logger()


# ==================== 系统提示词 ====================

def _resolve_file_path(filename: str, user_id: str, conversation_id: str) -> str:
    """
    根据文件名解析绝对路径。
    从 storage/chat/{user_id}/{conversation_id} 目录查找。
    如果 filename 本身是绝对路径且存在，则直接返回。
    """
    if os.path.isabs(filename) and os.path.exists(filename):
        return filename

    # 获取存储根路径
    # 假设 storage 目录在项目根目录下
    project_root = Path(__file__).parent.parent.parent
    chat_dir = project_root / "storage" / "chat" / user_id / conversation_id

    if not chat_dir.exists():
        return filename

    # 查找匹配的文件（考虑到文件名+下划线+时间戳的命名规则）
    # 比如 filename="test.docx", 存储的是 "test_20260120_160234.docx"
    name_part = Path(filename).stem
    extension = Path(filename).suffix

    # 尝试精确匹配或前缀匹配
    for file in chat_dir.iterdir():
        if file.name == filename:
            return str(file.absolute())
        if file.name.startswith(name_part) and file.name.endswith(extension):
            # 这里简单返回第一个匹配的，实际场景可能需要更精确的逻辑（比如最新一个）
            return str(file.absolute())

    return filename


def _load_prompt(filename: str) -> str:
    """从 backend/prompts 目录加载提示词文件"""
    try:
        prompt_path = Path(__file__).parent.parent / "prompts" / filename
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return ""
    except Exception:
        return ""


def _get_default_system_prompt() -> str:
    """获取默认系统提示词"""
    prompt = _load_prompt("chat_default.md")
    if prompt:
        return prompt
    return """你是 MCP 接口测试智能体的 AI 助手。你的职责是：

1. 帮助用户理解和使用接口测试功能
2. 回答关于 API 测试、测试用例生成的问题
3. 提供测试相关的建议和最佳实践
4. 解释测试报告和结果

请用友好、专业的语气回复用户。如果用户的问题超出你的能力范围，请诚实告知。"""


def _get_planning_system_prompt() -> str:
    """获取计划模式的系统提示词"""
    prompt = _load_prompt("chat_planning.md")
    if prompt:
        return prompt
    return """你是 MCP 接口测试智能体的 AI 助手，当前处于**计划模式**。

在计划模式下，你需要：
1. 理解用户的测试需求
2. 制定详细的测试计划，分解为多个子任务
3. 使用可用的 MCP 工具执行各个步骤
4. 在执行过程中展示你的思考过程

可用的工具：
- 你可以调用通过 MCP 协议动态注册的各种工具，如文档解析、测试生成、执行等。
- 请根据工具列表中的描述选择最合适的工具。

请在思考和规划时，先分析用户需求，然后制定清晰的步骤计划。"""


# ExecutionAssistant 已移除，所有工具执行由 ChatAgent 直接完成


# ==================== MCP 工具注册 ====================

async def register_mcp_tools(
    toolkit: Toolkit, 
    mcp_clients: Optional[List[StdIOStatefulClient]] = None,
    user_id: str = "",
    conversation_id: str = ""
) -> Toolkit:
    """
    使用 AgentScope 的有状态 MCP 客户端注册 MCP Server 工具到 Toolkit
    
    注意：StdIO MCP 服务器只有有状态客户端，需要维持长期连接。
    
    Args:
        toolkit: AgentScope Toolkit 实例
        mcp_clients: AgentScope 有状态 MCP 客户端列表 (StdIOStatefulClient)
        user_id: 用户ID（用于路径解析）
        conversation_id: 会话ID（用于路径解析）
        
    Returns:
        注册了工具 of Toolkit
    """
    
    # 使用 AgentScope 的有状态 MCP 客户端注册工具
    if mcp_clients:
        logger.info(f"[MCP] 正在注册 {len(mcp_clients)} 个有状态 MCP 客户端...")
        for client in mcp_clients:
            try:
                logger.info(f"[MCP] 注册客户端: {client.name}")
                await toolkit.register_mcp_client(client)
                logger.info(f"[MCP] 客户端 '{client.name}' 注册成功")
            except Exception as e:
                logger.error(f"[MCP] 注册客户端 '{client.name}' 失败: {e}", exc_info=True)
    
    return toolkit


# ==================== 会话管理 ====================

class Conversation:
    """
    对话会话类
    
    管理单个对话的消息历史，使用 AgentScope 的 Msg 和 InMemoryMemory。
    """
    
    def __init__(self, conversation_id: str):
        self.conversation_id = conversation_id
        self.messages: List[Msg] = []
        self.memory = InMemoryMemory()
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at
        # 计划模式状态
        self.plan_mode = False
        self.plan_notebook: Optional[PlanNotebook] = None
        # 计划更新队列，用于流式推送
        self.plan_update_queue: asyncio.Queue = asyncio.Queue()
    
    async def add_message(self, message: Msg):
        """添加消息到会话"""
        self.messages.append(message)
        await self.memory.add(message)
        self.updated_at = datetime.now().isoformat()
    
    def get_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取消息历史"""
        messages = self.messages[-limit:] if limit else self.messages
        return [self._msg_to_dict(msg) for msg in messages]
    
    def _msg_to_dict(self, msg: Msg) -> Dict[str, Any]:
        """将 Msg 转换为字典"""
        return {
            "name": msg.name,
            "role": msg.role,
            "content": msg.content,
            "timestamp": getattr(msg, 'timestamp', datetime.now().isoformat())
        }
    
    def get_memory(self) -> InMemoryMemory:
        """获取会话的 Memory 对象，用于 ReActAgent"""
        return self.memory
    
    def enable_plan_mode(self):
        """启用计划模式"""
        self.plan_mode = True
        if not self.plan_notebook:
            self.plan_notebook = PlanNotebook(
                max_subtasks=10,
                plan_to_hint=CustomPlanToHint()
            )
    
    def disable_plan_mode(self):
        """禁用计划模式"""
        self.plan_mode = False
    
    async def clear(self):
        """清空对话历史"""
        self.messages = []
        self.memory = InMemoryMemory()
        self.plan_mode = False
        self.plan_notebook = None
        self.updated_at = datetime.now().isoformat()


# ==================== Agent 工厂 ====================

# 定义一个 ContextVar 来存储当前请求的上下文数据
current_request_context = ContextVar("current_request_context", default=None)

class StreamingDashScopeChatModel(DashScopeChatModel):
    """
    包装 DashScopeChatModel 以支持流式输出到 output_queue
    """
    async def __call__(self, *args, **kwargs):
        # 从 ContextVar 获取当前请求的上下文
        ctx = current_request_context.get()
        
        # 如果没有上下文（例如内部调用或初始化测试），直接调用原模型
        if ctx is None:
            return await super().__call__(*args, **kwargs)
        
        queue = ctx.get("queue")
        
        # 强制开启流式以支持 token 拦截（AgentScope 的 ReActAgent 通常依赖此设置）
        kwargs["stream"] = True
        
        # 调用原模型
        res = await super().__call__(*args, **kwargs)
        
        # 拦截流式输出
        if hasattr(res, "content") and isinstance(res.content, AsyncGenerator):
            original_gen = res.content
            
            async def wrapped_gen():
                async for chunk in original_gen:
                    # 标记已有内容产出，用于兜底检查
                    ctx["has_yielded"] = True
                    
                    # 尝试从 chunk 中提取内容并推送到队列
                    if isinstance(chunk, dict):
                        text = chunk.get("text", "")
                        thinking = chunk.get("thinking", "")
                        if thinking:
                            await queue.put({"type": "thinking", "content": thinking})
                        if text:
                            await queue.put({"type": "chunk", "content": text})
                    elif isinstance(chunk, str):
                        await queue.put({"type": "chunk", "content": chunk})
                    
                    yield chunk
            
            res.content = wrapped_gen()
        
        return res

class AgentFactory:
    """智能体工厂类，用于创建不同角色的智能体"""
    
    def __init__(self, model_config: Optional[ModelConfig] = None):
        self.logger = get_logger()
        # 如果未提供配置，尝试通过配置管理器获取
        if model_config is None:
            config_manager = get_config_manager()
            self.model_config = config_manager.get_config("model") or ModelConfig()
        else:
            self.model_config = model_config
            
        self.logger.info(f"AgentFactory 初始化，模型名称: {self.model_config.model_name}")
        
        # 获取 API Key，优先从环境变量获取，然后从配置获取
        self.api_key = os.environ.get("DASHSCOPE_API_KEY") or self.model_config.api_key
        
        if not self.api_key or "{YOUR_DASHSCOPE_API_KEY}" in self.api_key:
            self.logger.error("未找到有效的 DASHSCOPE_API_KEY，请在环境变量或 model.toml 中配置")
            # 不在这里直接 raise，允许工厂创建，但在调用时校验
        else:
            # 打印脱敏后的 Key 方便排查
            masked_key = f"{self.api_key[:4]}...{self.api_key[-4:]}" if len(self.api_key) > 8 else "****"
            self.logger.info(f"成功加载 API Key: {masked_key}")
        
        # 初始化共享模型，使用包装后的流式模型
        self.model = StreamingDashScopeChatModel(
            model_name=self.model_config.model_name,
            api_key=self.api_key,
            stream=True, # 始终开启 stream 以便拦截
            enable_thinking=self.model_config.enable_thinking,
        )

    async def _plan_agent_post_acting_hook(self, agent: ReActAgent, kwargs: dict, output: Any) -> Any:
        """
        动作执行后的钩子，用于检测计划更新并触发回调
        """
        if hasattr(agent, "plan_notebook") and agent.plan_notebook and agent.plan_notebook.current_plan:
            # 获取当前计划数据的字典形式
            plan_data = agent.plan_notebook.current_plan.model_dump()
            
            # 如果智能体绑定了更新回调，则调用它
            if hasattr(agent, "on_plan_update_callback") and agent.on_plan_update_callback:
                try:
                    callback = agent.on_plan_update_callback
                    if asyncio.iscoroutinefunction(callback):
                        await callback(plan_data)
                    else:
                        callback(plan_data)
                except Exception as e:
                    self.logger.error(f"执行计划更新回调失败: {e}")
        return output

    def create_agent(
        self,
        agent_type: str = "chat",
        name: str = "Assistant",
        system_prompt: Optional[str] = None,
        memory: Optional[InMemoryMemory] = None,
        toolkit: Optional[Toolkit] = None,
        plan_notebook: Optional[PlanNotebook] = None,
        plan_update_callback: Optional[Callable] = None
    ) -> ReActAgent:
        """
        根据类型创建智能体
        """
        if not self.api_key or "{YOUR_DASHSCOPE_API_KEY}" in self.api_key:
            raise ValueError("DASHSCOPE_API_KEY 未配置或无效，请检查环境变量或 model.toml")
            
        # 选择格式化器和提示词
        if agent_type == "chat":
            formatter = DashScopeChatFormatter()
            default_prompt = _get_default_system_prompt()
        elif agent_type == "plan":
            formatter = DashScopeMultiAgentFormatter()
            default_prompt = _get_planning_system_prompt()
        elif agent_type == "exe":
            formatter = DashScopeMultiAgentFormatter()
            default_prompt = _get_execution_system_prompt()
        else:
            formatter = DashScopeChatFormatter()
            default_prompt = _get_default_system_prompt()
            
        agent_kwargs = {
            "name": name,
            "sys_prompt": system_prompt or default_prompt,
            "model": self.model,
            "formatter": formatter,
            "toolkit": toolkit or Toolkit(),
            "memory": memory or InMemoryMemory(),
        }
        
        if plan_notebook is not None:
            agent_kwargs["plan_notebook"] = plan_notebook
            
        agent = ReActAgent(**agent_kwargs)
        
        # 如果是计划相关智能体，注册钩子
        if agent_type in ["plan", "exe"]:
            # 绑定回调
            if plan_update_callback:
                agent.on_plan_update_callback = plan_update_callback
            
            # 注册实例级 post_acting 钩子
            agent.register_instance_hook(
                hook_type="post_acting",
                hook_name="plan_update_detector",
                hook=lambda kwargs, output, agent=agent: self._plan_agent_post_acting_hook(agent, kwargs, output)
            )
            
        return agent


# ==================== Agent 创建 (兼容旧代码) ====================

def create_react_agent(
    name: str = "Assistant",
    system_prompt: Optional[str] = None,
    memory: Optional[InMemoryMemory] = None,
    toolkit: Optional[Toolkit] = None,
    plan_notebook: Optional[PlanNotebook] = None,
    enable_thinking: bool = False
) -> ReActAgent:
    """创建 ReActAgent 实例 (使用工厂重构)"""
    factory = AgentFactory()
    return factory.create_agent(
        agent_type="chat",
        name=name,
        system_prompt=system_prompt,
        memory=memory,
        toolkit=toolkit,
        plan_notebook=plan_notebook
    )


async def create_planning_agent(
    memory: Optional[InMemoryMemory] = None,
    plan_notebook: Optional[PlanNotebook] = None,
    mcp_clients: Optional[List[StdIOStatefulClient]] = None,
    user_id: str = "",
    conversation_id: str = ""
) -> ReActAgent:
    """创建计划模式的 Agent (使用工厂重构)"""
    toolkit = Toolkit()
    await register_mcp_tools(toolkit, mcp_clients, user_id, conversation_id)
    
    factory = AgentFactory()
    # 默认使用 plan 类型
    return factory.create_agent(
        agent_type="plan",
        name="PlanningAssistant",
        system_prompt=_get_planning_system_prompt(),
        memory=memory,
        toolkit=toolkit,
        plan_notebook=plan_notebook or PlanNotebook(
            max_subtasks=10,
            plan_to_hint=CustomPlanToHint()
        )
    )


# ==================== 聊天服务 ====================

class ChatService:
    """
    聊天服务
    
    管理多个对话会话，提供高层 API 接口。
    基于 AgentScope ReActAgent 实现。
    支持计划模式（/plan 命令）。
    """
    
    PLAN_COMMAND_PREFIX = "/plan"
    
    def __init__(
        self, 
        database: Database, 
        mcp_clients: Optional[List[StdIOStatefulClient]] = None,
        system_prompt: Optional[str] = None,
        model_config: Optional[ModelConfig] = None
    ):
        """
        初始化聊天服务
        
        Args:
            database: 数据库实例
            mcp_clients: AgentScope 有状态 MCP 客户端列表
            system_prompt: 自定义系统提示词
            model_config: 模型配置
        """
        self.logger = get_logger()
        self.database = database
        self.mcp_clients = mcp_clients or []
        self.system_prompt = system_prompt or _get_default_system_prompt()
        
        # 初始化智能体工厂
        self.factory = AgentFactory(model_config)
        
        # 会话存储（内存中，保留用于上下文管理）
        self.conversations: Dict[str, Conversation] = {}
        
        # 配置
        self.max_context_messages = 20  # 最大上下文消息数
        
        self.logger.info("ChatService 初始化完成（使用 ReActAgent，支持计划模式）")
        
        # 预初始化常用智能体（作为模版）
        self._init_agent_templates()

    def _init_agent_templates(self):
        """预初始化智能体模版，加快响应速度"""
        try:
            self.logger.info("[ChatService] 正在预初始化智能体模版...")
            # 这里的创建仅为了确保模型和基础组件加载完成
            self.factory.create_agent(agent_type="chat", name="TemplateAssistant")
            self.factory.create_agent(agent_type="plan", name="TemplatePlanner")
            # ExecutionAssistant 已移除
            self.logger.info("[ChatService] 智能体模版预初始化完成")
        except Exception as e:
            self.logger.error(f"[ChatService] 预初始化智能体失败: {e}")
    
    def _is_plan_command(self, message: str) -> bool:
        """检查消息是否是计划命令"""
        return message.strip().lower().startswith(self.PLAN_COMMAND_PREFIX)
    
    def _extract_plan_content(self, message: str) -> str:
        """提取计划命令的内容"""
        content = message.strip()[len(self.PLAN_COMMAND_PREFIX):].strip()
        return content if content else "请帮我制定一个测试计划"
    
    async def _restore_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """从数据库恢复会话到内存"""
        try:
            db_conv = self.database.get_conversation(conversation_id)
            if not db_conv:
                return None
            
            conversation = Conversation(conversation_id)
            # 加载最近的历史消息作为上下文
            messages = self.database.list_conversation_messages(
                conversation_id, 
                limit=self.max_context_messages
            )
            
            for msg_data in messages:
                msg = Msg(
                    name="User" if msg_data['role'] == "user" else "Assistant",
                    role=msg_data['role'],
                    content=msg_data['content']
                )
                await conversation.add_message(msg)
            
            self.conversations[conversation_id] = conversation
            self.logger.info(
                f"[ChatService] 从数据库恢复会话 | "
                f"conversation_id: {conversation_id} | 消息数: {len(messages)}"
            )
            return conversation
        except Exception as e:
            self.logger.error(f"[ChatService] 恢复会话失败: {str(e)}", exc_info=True)
            return None

    async def _get_or_create_conversation(
        self, 
        message: str, 
        user_id: str, 
        conversation_id: Optional[str]
    ) -> tuple[str, Conversation]:
        """获取或创建会话"""
        if conversation_id and conversation_id in self.conversations:
            return conversation_id, self.conversations[conversation_id]
        
        if conversation_id:
            # 尝试从数据库恢复
            conversation = await self._restore_conversation(conversation_id)
            if conversation:
                return conversation_id, conversation
            # 如果数据库也没有，创建新会话
            conversation = Conversation(conversation_id)
            self.conversations[conversation_id] = conversation
            self.logger.info(
                f"[ChatService] 创建新内存会话(ID已提供) | "
                f"conversation_id: {conversation_id}"
            )
            return conversation_id, conversation
        
        # 创建全新会话
        conversation_id = str(uuid.uuid4())
        # 创建数据库对话
        self.database.create_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            title=message[:50]  # 使用前50个字符作为标题
        )
        
        conversation = Conversation(conversation_id)
        self.conversations[conversation_id] = conversation
        self.logger.info(f"[ChatService] 初始化新会话 | conversation_id: {conversation_id}")
        return conversation_id, conversation

    def _extract_thinking_and_content(self, response_content: Any) -> tuple[str, str]:
        """
        从响应内容中提取思考过程和最终回复
        
        Args:
            response_content: 响应内容（可能是字符串、列表或其他格式）
            
        Returns:
            (thinking, content) 思考过程和最终内容的元组
        """
        # 添加调试日志
        self.logger.debug(
            f"[_extract_thinking_and_content] 原始内容 | "
            f"type: {type(response_content)} | "
            f"content: {str(response_content)[:500]}"
        )
        
        thinking = ""
        content = ""
        
        if isinstance(response_content, list):
            # 处理列表格式（如 [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": "..."}]）
            for item in response_content:
                if isinstance(item, dict):
                    if item.get("type") == "thinking" or "thinking" in item:
                        thinking += item.get("thinking", "")
                    elif item.get("type") == "text" or "text" in item:
                        content += item.get("text", "")
                else:
                    content += str(item)
        elif isinstance(response_content, dict):
            thinking = response_content.get("thinking", "")
            content = response_content.get("text", "") or response_content.get("content", "")
        elif isinstance(response_content, str):
            content = response_content
        else:
            content = str(response_content) if response_content else ""
        
        self.logger.debug(
            f"[_extract_thinking_and_content] 提取结果 | "
            f"thinking: {thinking[:200] if thinking else 'None'} | "
            f"content: {content[:200] if content else 'None'}"
        )
        
        return thinking, content

    async def _get_agent(
        self,
        conversation: Conversation,
        user_id: str,
        conversation_id: str,
        plan_update_callback: Optional[Callable] = None
    ) -> ReActAgent:
        """根据会话状态获取合适的智能体"""
        toolkit = Toolkit()
        await register_mcp_tools(toolkit, self.mcp_clients, user_id, conversation_id)
        
        if conversation.plan_mode:
            # 计划模式：使用计划智能体（已移除执行智能体）
            plan_notebook = conversation.plan_notebook
            return self.factory.create_agent(
                agent_type="plan",
                name="PlanningAssistant",
                memory=conversation.get_memory(),
                toolkit=toolkit,
                plan_notebook=plan_notebook,
                plan_update_callback=plan_update_callback
            )
        else:
            # 普通模式：ChatAgent 直接执行所有工具
            return self.factory.create_agent(
                agent_type="chat",
                name="Assistant",
                system_prompt=self.system_prompt,
                memory=conversation.get_memory(),
                toolkit=toolkit,
                plan_update_callback=plan_update_callback
            )
            
    async def send_message(
        self,
        message: str,
        user_id: str,
        conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        发送消息并获取回复（异步）
        
        Args:
            message: 用户消息
            user_id: 用户 ID
            conversation_id: 会话ID（可选，为空时创建新会话）
            
        Returns:
            包含回复和会话ID的字典
        """
        is_plan_mode = self._is_plan_command(message)
        actual_message = self._extract_plan_content(message) if is_plan_mode else message
        
        self.logger.info(
            f"[ChatService] 收到消息 | conversation_id: {conversation_id} | "
            f"消息长度: {len(message)} | 计划模式: {is_plan_mode}"
        )
        
        # 获取或创建会话
        conversation_id, conversation = await self._get_or_create_conversation(
            message, user_id, conversation_id
        )
        
        # 如果是计划模式，启用计划功能
        if is_plan_mode:
            conversation.enable_plan_mode()
        
        # 保存用户消息到数据库
        user_message_id = str(uuid.uuid4())
        self.database.create_message(
            message_id=user_message_id,
            conversation_id=conversation_id,
            role="user",
            content=message
        )
        
        # 创建用户消息 Msg
        user_msg = Msg(name="User", role="user", content=actual_message)
        await conversation.add_message(user_msg)
        
        thinking = ""
        reply_content = ""
        
        try:
            # 获取合适的智能体
            agent = await self._get_agent(conversation, user_id, conversation_id)
            
            # 调用 Agent 生成回复
            start_time = time.time()
            response_msg = await agent(user_msg)
            elapsed = time.time() - start_time
            
            self.logger.info(f"[ChatService] ReActAgent 调用成功 | 耗时: {elapsed:.2f}s")
            
            # 提取思考过程和回复内容
            if response_msg:
                thinking, reply_content = self._extract_thinking_and_content(response_msg.content)
            
            if not reply_content:
                reply_content = "抱歉，无法生成有效回复。"
            
        except Exception as e:
            self.logger.error(f"[ChatService] ReActAgent 调用失败: {str(e)}", exc_info=True)
            reply_content = f"抱歉，处理消息时发生错误: {str(e)}"
        
        # 保存助手消息到数据库
        assistant_message_id = str(uuid.uuid4())
        self.database.create_message(
            message_id=assistant_message_id,
            conversation_id=conversation_id,
            role="assistant",
            content=reply_content
        )
        
        # 创建助手回复 Msg 并添加到会话
        assistant_msg = Msg(name="Assistant", role="assistant", content=reply_content)
        await conversation.add_message(assistant_msg)
        
        self.logger.info(
            f"[ChatService] 回复生成完成 | conversation_id: {conversation_id} | "
            f"回复长度: {len(reply_content)} | 思考长度: {len(thinking)}"
        )
        
        result = {
            "conversation_id": conversation_id,
            "reply": reply_content,
            "timestamp": datetime.now().isoformat(),
            "plan_mode": conversation.plan_mode
        }
        
        # 如果有思考过程，添加到结果中
        if thinking:
            result["thinking"] = thinking
        
        return result
    
    async def send_message_streaming(
        self,
        message: str,
        user_id: str,
        conversation_id: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        发送消息并获取流式回复（异步生成器）
        
        使用 MsgHub 进行多智能体协作，并捕获计划更新。
        """
        is_plan_mode = self._is_plan_command(message)
        actual_message = self._extract_plan_content(message) if is_plan_mode else message
        
        self.logger.info(
            f"[ChatService] 收到消息（流式）| conversation_id: {conversation_id} | "
            f"消息长度: {len(message)} | 计划模式: {is_plan_mode}"
        )
        
        # 获取或创建会话
        conversation_id, conversation = await self._get_or_create_conversation(
            message, user_id, conversation_id
        )
        
        # 如果是计划模式，启用计划功能
        if is_plan_mode:
            conversation.enable_plan_mode()
        
        # 保存用户消息到数据库
        user_message_id = str(uuid.uuid4())
        self.database.create_message(
            message_id=user_message_id,
            conversation_id=conversation_id,
            role="user",
            content=message
        )
        
        # 创建用户消息 Msg
        user_msg = Msg(name="User", role="user", content=actual_message)
        await conversation.add_message(user_msg)
        
        # 先发送会话ID和模式信息
        yield {
            "type": "start",
            "conversation_id": conversation_id,
            "plan_mode": conversation.plan_mode
        }
        
        try:
            # 清空之前的计划更新队列
            while not conversation.plan_update_queue.empty():
                conversation.plan_update_queue.get_nowait()

            # 计划更新回调
            async def on_plan_update(plan_data):
                await conversation.plan_update_queue.put(plan_data)

            # 准备工具集
            self.logger.info(f"[ChatService] 正在注册 MCP 工具... conversation_id: {conversation_id}")
            toolkit = Toolkit()
            await register_mcp_tools(toolkit, self.mcp_clients, user_id, conversation_id)
            
            # 列出最终可用的工具
            available_tools = list(toolkit.tools.keys()) if hasattr(toolkit, "tools") else "未知"
            self.logger.info(f"[ChatService] MCP 工具注册完成，当前可用工具: {available_tools}")

            # 确定参与者和主智能体
            participants = []
            task_agent = None
            
            # ChatAgent 始终参与并负责所有工具执行（已移除 ExecutionAssistant）
            chat_agent = self.factory.create_agent(
                agent_type="chat", 
                name="Assistant", 
                memory=conversation.get_memory(),
                system_prompt=self.system_prompt,
                toolkit=toolkit
            )
            participants.append(chat_agent)
            
            if is_plan_mode:
                # 规划阶段：Chat + Plan
                task_agent = self.factory.create_agent(
                    agent_type="plan", 
                    name="PlanningAssistant", 
                    memory=conversation.get_memory(), 
                    plan_notebook=conversation.plan_notebook, 
                    plan_update_callback=on_plan_update,
                    toolkit=toolkit
                )
                participants.append(task_agent)

            # 输出队列用于汇聚不同来源的消息
            output_queue = asyncio.Queue()
            full_reply = []

            async def run_agents():
                try:
                    self.logger.info(f"[ChatService] 启动多智能体协作流... 参与者: {[p.name for p in participants]}")
                    
                    # 彻底移除 stream_printing_messages 依赖，改为直接驱动并利用模型包装器捕获流
                    # 设置 ContextVar 以便模型包装器能找到 output_queue
                    ctx = {"queue": output_queue, "has_yielded": False}
                    token = current_request_context.set(ctx)
                    
                    try:
                        async with MsgHub(participants=participants) as hub:
                            # 1. 首先让 chat_agent 回复用户
                            self.logger.info(f"[ChatService] 正在请求 ChatAgent 回复...")
                            
                            # 直接调用 agent，流式 token 会由 StreamingDashScopeChatModel 自动推送到 output_queue
                            res = await chat_agent(user_msg)
                            
                            thinking, content = self._extract_thinking_and_content(res.content)
                            if content:
                                # 只有当模型没有产出流式内容时，才手动推送内容（兜底）
                                if not ctx["has_yielded"]:
                                    await output_queue.put({"type": "chunk", "content": content})
                                full_reply.append(content)
                            
                            # 2. 如果有任务智能体且需要后续操作，触发任务智能体
                            if task_agent:
                                self.logger.info(f"[ChatService] 正在请求 TaskAgent ({task_agent.name}) 执行后续任务...")
                                task_res = await task_agent()
                                
                                t_thinking, t_content = self._extract_thinking_and_content(task_res.content)
                                if t_content:
                                    if not ctx["has_yielded"]: # 这里 has_yielded 可能被重置，但在本设计中它标记整个请求过程是否有流
                                         # 实际上每个 agent 调用后我们都可以检查
                                         pass
                                    full_reply.append(t_content)
                    except Exception as e:
                        self.logger.error(f"[ChatService] Agent 协作逻辑执行失败: {e}", exc_info=True)
                        raise e
                    finally:
                        current_request_context.reset(token)
                        
                except Exception as e:
                    self.logger.error(f"Agent 执行出错: {e}", exc_info=True)
                    await output_queue.put({"type": "error", "content": str(e)})
                finally:
                    await output_queue.put(None) # 结束标记

            async def watch_plan_updates():
                while True:
                    try:
                        plan_data = await conversation.plan_update_queue.get()
                        await output_queue.put({"type": "plan_update", "data": plan_data})
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        self.logger.error(f"监听计划更新出错: {e}")

            # 启动协程任务
            agent_task = asyncio.create_task(run_agents())
            watch_task = asyncio.create_task(watch_plan_updates())

            try:
                while True:
                    item = await output_queue.get()
                    if item is None:
                        break
                    if item["type"] == "error":
                        yield {"type": "chunk", "content": f"\n[Error] {item['content']}"}
                        break
                    yield item
            finally:
                agent_task.cancel()
                watch_task.cancel()
                try:
                    await asyncio.gather(agent_task, watch_task, return_exceptions=True)
                except:
                    pass

        except Exception as e:
            self.logger.error(f"[ChatService] 准备流式输出失败: {e}", exc_info=True)
            yield {"type": "chunk", "content": f"准备失败: {str(e)}"}

        # 保存助手回复到数据库和内存
        reply_content = "".join(full_reply)
        if reply_content:
            assistant_message_id = str(uuid.uuid4())
            self.database.create_message(
                message_id=assistant_message_id,
                conversation_id=conversation_id,
                role="assistant",
                content=reply_content
            )
            assistant_msg = Msg(name="Assistant", role="assistant", content=reply_content)
            await conversation.add_message(assistant_msg)

        yield {
            "type": "done",
            "conversation_id": conversation_id,
            "timestamp": datetime.now().isoformat(),
            "plan_mode": conversation.plan_mode
        }

    # 同步包装器已移除，以避免在已有事件循环中产生死锁。
    # 如果需要同步调用，请在外部使用 asyncio.run() 或类似机制。
