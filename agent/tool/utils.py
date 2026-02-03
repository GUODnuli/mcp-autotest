"""
Legacy utility tools for file operations.

DEPRECATED: These tools are being replaced by base tools in tool.base package:
- safe_view_text_file -> tool.base.file_read.read_file
- safe_write_text_file -> tool.base.file_write.write_file
- list_uploaded_files -> kept for backward compatibility (conversation-specific)

New code should use the base tools which provide:
- Workspace-scoped security via ToolConfig
- Consistent error handling
- Cross-platform support

These legacy tools are kept for backward compatibility during migration.
They will be removed in a future version.
"""

from pathlib import Path
import json
from agentscope.tool import ToolResponse
from agentscope.message import TextBlock

# 获取项目根目录的绝对路径（避免工作目录不一致问题）
PROJECT_ROOT = Path(__file__).parent.parent.parent
STORAGE_CHAT_DIR = (PROJECT_ROOT / "storage" / "chat").resolve()
STORAGE_CACHE_DIR = (PROJECT_ROOT / "storage" / "cache").resolve()


def list_uploaded_files(user_id: str, conversation_id: str) -> ToolResponse:
    """
    List all files uploaded by user in current conversation.
    
    Args:
        user_id: The user ID
        conversation_id: The conversation ID
        
    Returns:
        List of uploaded files with their absolute paths
    """
    # 基础目录（用于安全校验）
    base_dir = STORAGE_CHAT_DIR
    upload_dir = (base_dir / user_id / conversation_id).resolve()
    
    # 路径安全校验：防止路径遍历攻击
    try:
        upload_dir.relative_to(base_dir)
    except ValueError:
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text="Error: Access denied (path traversal detected)."
            )]
        )
    
    if not upload_dir.exists():
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=f"No files uploaded yet for user {user_id} in conversation: {conversation_id}"
            )]
        )
    
    files = [f for f in upload_dir.iterdir() if f.is_file()]
    if not files:
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=f"Upload directory exists but is empty for user {user_id} in conversation: {conversation_id}"
            )]
        )
    
    # 返回相对于 storage/chat 的路径
    file_list = "\n".join([
        f"- {f.name} (path: {user_id}/{conversation_id}/{f.name})"
        for f in files
    ])
    
    return ToolResponse(
        content=[TextBlock(
            type="text",
            text=f"Uploaded files in conversation {conversation_id}:\n{file_list}"
        )]
    )


def safe_view_text_file(file_path: str) -> ToolResponse:
    """
    Safely view text file content with path traversal protection.
    
    Args:
        file_path: The file path to read (relative to storage/chat)
        
    Returns:
        ToolResponse containing file content or error message
    """
    try:
        # 基础目录（用于安全校验）
        base_dir = STORAGE_CHAT_DIR

        # 处理路径：相对于 base_dir 解析
        target_path = (base_dir / file_path).resolve()

        # 路径安全校验
        try:
            target_path.relative_to(base_dir)
        except ValueError:
            raise PermissionError(
                f"Access denied: {file_path} is outside allowed directory (storage/chat)"
            )

        # 检查文件是否存在
        if not target_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not target_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        # 读取文件内容
        content = target_path.read_text(encoding='utf-8')

        # ✅ 正确返回 ToolResponse
        return ToolResponse(
            content=[TextBlock(type="text", text=content)]
        )

    except Exception as e:
        # ✅ 错误也必须返回 ToolResponse
        return ToolResponse(
            content=[TextBlock(type="text", text=f"Error: {str(e)}")]
        )


def safe_write_text_file(file_path: str, content: str) -> ToolResponse:
    """
    Write text content to a file safely (restricted to storage/cache directory).
    
    All files will be saved to storage/cache directory to prevent polluting
    the project root. The file_path parameter will be treated as filename only.
    
    Args:
        file_path: Filename (or path, but only filename will be used)
        content: Text content to write
        
    Returns:
        ToolResponse with success message and actual file path
        
    Example:
        safe_write_text_file("test_results.json", json.dumps(data))
        # File will be saved to: storage/cache/test_results.json
    """
    try:
        # 确保 cache 目录存在
        STORAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        
        # 只取文件名，防止路径遍历攻击
        filename = Path(file_path).name
        
        # 限制文件名长度
        if len(filename) > 255:
            return ToolResponse(
                content=[TextBlock(
                    type="text",
                    text="Error: Filename too long (max 255 characters)"
                )]
            )
        
        # 构造安全的目标路径
        target_path = (STORAGE_CACHE_DIR / filename).resolve()
        
        # 验证路径在允许的范围内
        try:
            target_path.relative_to(STORAGE_CACHE_DIR)
        except ValueError:
            return ToolResponse(
                content=[TextBlock(
                    type="text",
                    text="Error: Access denied (path traversal detected)"
                )]
            )
        
        # 写入文件
        target_path.write_text(content, encoding='utf-8')
        
        # 返回成功消息
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=f"File saved successfully to: {target_path}\nFile size: {len(content)} bytes"
            )]
        )
        
    except Exception as e:
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=f"Error writing file: {str(e)}"
            )]
        )
