# -*- coding: utf-8 -*-
"""
File write tool - Secure file writing within workspace.

Provides file writing with:
- Path validation against workspace boundary
- Write permission checking
- Sensitive file protection
- Parent directory creation
- Byte count reporting
"""

import json
from pathlib import Path

from agentscope.tool import ToolResponse
from agentscope.message import TextBlock

from .config import ToolConfig


def _success_response(data: dict) -> ToolResponse:
    """Create a success ToolResponse."""
    return ToolResponse(
        content=[TextBlock(type="text", text=json.dumps(data, ensure_ascii=False))]
    )


def _error_response(message: str, error_code: str = "WRITE_ERROR") -> ToolResponse:
    """Create an error ToolResponse."""
    return ToolResponse(
        content=[TextBlock(
            type="text",
            text=json.dumps({
                "status": "error",
                "error_code": error_code,
                "message": message
            }, ensure_ascii=False)
        )]
    )


def write_file(file_path: str, content: str) -> ToolResponse:
    """
    Write content to a file in the workspace.

    Creates or overwrites a file with the provided content.
    Requires write permission and validates path is within workspace.

    Args:
        file_path: Path to file (relative to workspace or absolute)
        content: Text content to write to the file

    Returns:
        ToolResponse containing:
        - status: "success" or "error"
        - file_path: Absolute path to the written file
        - bytes_written: Number of bytes written
        - created: True if file was created, False if overwritten

    Example:
        write_file("output/result.json", '{"key": "value"}')
        write_file("src/new_module.py", "# New module\\n")

    Security Notes:
        - Requires write permission (--writePermission true)
        - Path must be within workspace boundary
        - Sensitive files (.env, credentials, etc.) are blocked
        - Parent directories are created automatically
    """
    try:
        config = ToolConfig.get()
    except RuntimeError as e:
        return _error_response(str(e), "CONFIG_ERROR")

    # Check write permission
    if not config.is_write_allowed(file_path):
        if not config.write_permission:
            return _error_response(
                "Write permission denied. Start agent with --writePermission true",
                "PERMISSION_DENIED"
            )
        return _error_response(
            f"Access denied: '{file_path}' is outside the workspace boundary",
            "ACCESS_DENIED"
        )

    # Check for sensitive files
    if config.is_sensitive(file_path):
        return _error_response(
            f"Cannot write to sensitive file: {file_path}. "
            "Credentials, keys, and .env files are protected.",
            "SENSITIVE_FILE"
        )

    # Resolve the full path
    target_path = config.resolve_path(file_path)

    # Validate content
    if content is None:
        return _error_response("Content cannot be None", "INVALID_CONTENT")

    # Validate filename length
    if len(target_path.name) > 255:
        return _error_response(
            f"Filename too long: {len(target_path.name)} chars (max 255)",
            "FILENAME_TOO_LONG"
        )

    try:
        # Track if file existed before
        existed = target_path.exists()

        # Create parent directories if needed
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Write the file
        bytes_written = target_path.write_text(content, encoding="utf-8")

        return _success_response({
            "status": "success",
            "file_path": str(target_path),
            "bytes_written": len(content.encode("utf-8")),
            "created": not existed,
            "message": f"Successfully {'created' if not existed else 'updated'} {file_path}"
        })

    except PermissionError:
        return _error_response(
            f"Permission denied: cannot write to {file_path}",
            "PERMISSION_DENIED"
        )

    except OSError as e:
        return _error_response(
            f"OS error writing file: {e}",
            "OS_ERROR"
        )

    except Exception as e:
        return _error_response(
            f"Failed to write file: {type(e).__name__}: {e}",
            "WRITE_ERROR"
        )
