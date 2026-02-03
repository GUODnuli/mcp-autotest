# -*- coding: utf-8 -*-
"""
File read tool - Secure file reading within workspace.

Provides file reading with:
- Path validation against workspace boundary
- Line-based pagination (offset/limit)
- Line number prefixes (cat -n style)
- Truncation for long lines
- Binary/image file detection
"""

import json
from pathlib import Path
from typing import Optional

from agentscope.tool import ToolResponse
from agentscope.message import TextBlock

from .config import ToolConfig


def _success_response(data: dict) -> ToolResponse:
    """Create a success ToolResponse."""
    return ToolResponse(
        content=[TextBlock(type="text", text=json.dumps(data, ensure_ascii=False))]
    )


def _error_response(message: str, error_code: str = "READ_ERROR") -> ToolResponse:
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


def _text_response(text: str) -> ToolResponse:
    """Create a plain text ToolResponse (for file content)."""
    return ToolResponse(
        content=[TextBlock(type="text", text=text)]
    )


# Binary file extensions that shouldn't be read as text
_BINARY_EXTENSIONS = {
    ".exe", ".dll", ".so", ".dylib", ".bin",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svg",
    ".mp3", ".wav", ".ogg", ".flac", ".aac",
    ".mp4", ".avi", ".mkv", ".mov", ".webm",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".pyc", ".pyo", ".class", ".o", ".obj",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".db", ".sqlite", ".sqlite3",
}


def read_file(
    file_path: str,
    offset: int = 0,
    limit: int = 2000
) -> ToolResponse:
    """
    Read a text file from the workspace with line numbers.

    Reads files within the workspace boundary, returning content with
    line numbers (cat -n style). Supports pagination via offset/limit.

    Args:
        file_path: Path to file (relative to workspace or absolute)
        offset: Line number to start reading from (0-indexed, default 0)
        limit: Maximum number of lines to read (default 2000)

    Returns:
        ToolResponse containing file content with line numbers:
        ```
        1	first line content
        2	second line content
        ...
        ```

        On error, returns JSON with status, error_code, and message.

    Example:
        read_file("src/main.py")
        read_file("config/settings.json", offset=100, limit=50)

    Notes:
        - Lines longer than 2000 characters are truncated
        - Binary files (images, executables, etc.) return an error
        - Empty files return a warning message
        - Path must be within workspace boundary
    """
    try:
        config = ToolConfig.get()
    except RuntimeError as e:
        return _error_response(str(e), "CONFIG_ERROR")

    # Validate path is within workspace
    if not config.is_path_allowed(file_path):
        return _error_response(
            f"Access denied: '{file_path}' is outside the workspace boundary",
            "ACCESS_DENIED"
        )

    # Resolve the full path - try workspace first, then other allowed paths
    target_path = config.resolve_path(file_path)

    # If not found in workspace, search other allowed paths
    if not target_path.exists():
        file_path_obj = Path(file_path)
        if not file_path_obj.is_absolute():
            for allowed_path in config.allowed_paths:
                candidate = (allowed_path / file_path_obj).resolve()
                if candidate.exists() and config.is_path_allowed(candidate):
                    target_path = candidate
                    break

    # Check if file exists
    if not target_path.exists():
        return _error_response(
            f"File not found: {file_path}",
            "FILE_NOT_FOUND"
        )

    # Check if it's a file (not directory)
    if not target_path.is_file():
        return _error_response(
            f"Path is not a file: {file_path}",
            "NOT_A_FILE"
        )

    # Check for binary files
    suffix = target_path.suffix.lower()
    if suffix in _BINARY_EXTENSIONS:
        return _error_response(
            f"Cannot read binary file ({suffix}). Use appropriate tool for this file type.",
            "BINARY_FILE"
        )

    # Validate offset and limit
    offset = max(0, offset)
    limit = max(1, min(limit, 10000))  # Cap at 10000 lines

    try:
        # Read file content
        content = target_path.read_text(encoding="utf-8")

        # Handle empty files
        if not content:
            return _text_response(f"[File is empty: {file_path}]")

        # Split into lines
        lines = content.splitlines()
        total_lines = len(lines)

        # Handle offset beyond file length
        if offset >= total_lines:
            return _text_response(
                f"[Offset {offset} is beyond end of file ({total_lines} lines)]"
            )

        # Extract requested lines
        selected_lines = lines[offset:offset + limit]

        # Format with line numbers (1-indexed for display)
        max_line_width = 2000
        formatted_lines = []
        for idx, line in enumerate(selected_lines, start=offset + 1):
            # Truncate long lines
            if len(line) > max_line_width:
                line = line[:max_line_width] + "... [truncated]"
            # Format as: "   123\tcontent"
            formatted_lines.append(f"{idx:>6}\t{line}")

        result = "\n".join(formatted_lines)

        # Add metadata header if paginated
        if offset > 0 or offset + limit < total_lines:
            header = f"[Showing lines {offset + 1}-{min(offset + limit, total_lines)} of {total_lines} total]\n"
            result = header + result

        return _text_response(result)

    except UnicodeDecodeError:
        return _error_response(
            f"Cannot decode file as UTF-8. File may be binary or use different encoding.",
            "DECODE_ERROR"
        )

    except PermissionError:
        return _error_response(
            f"Permission denied: cannot read {file_path}",
            "PERMISSION_DENIED"
        )

    except Exception as e:
        return _error_response(
            f"Failed to read file: {type(e).__name__}: {e}",
            "READ_ERROR"
        )
