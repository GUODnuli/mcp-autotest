# -*- coding: utf-8 -*-
"""ChatAgent 常量定义"""

NAME_APP = "TestAgent"
NAME_AGENT = "ChatAgent"

# Session 文件 ID
CHAT_SESSION_ID = "session"

# Socket.IO 命名空间
NAMESPACE_AGENT = "/agent"
NAMESPACE_CLIENT = "/client"

# Socket.IO 事件名
EVENT_INTERRUPT = "interrupt"
EVENT_PUSH_REPLIES = "pushReplies"
EVENT_PUSH_REPLYING_STATE = "pushReplyingState"

# 消息类型
BLOCK_TYPE_TEXT = "text"
BLOCK_TYPE_THINKING = "thinking"
BLOCK_TYPE_TOOL_USE = "tool_use"
BLOCK_TYPE_TOOL_RESULT = "tool_result"
