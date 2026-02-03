# -*- coding: utf-8 -*-
"""
File edit tool - Exact string replacement in files.

Provides file editing with:
- Exact string matching and replacement
- Uniqueness validation (unless replace_all)
- Path and permission validation
- Diff-like change summary
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


def _error_response(message: str, error_code: str = "EDIT_ERROR") -> ToolResponse:
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


def edit_file(
    file_path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False
) -> ToolResponse:
    """
    Perform exact string replacement in a file.

    Replaces occurrences of old_string with new_string in the specified file.
    By default, requires old_string to be unique; use replace_all=True for
    multiple replacements.

    Args:
        file_path: Path to file (relative to workspace or absolute)
        old_string: Exact string to find and replace
        new_string: String to replace old_string with
        replace_all: If True, replace all occurrences. If False, old_string
                     must appear exactly once (default False)

    Returns:
        ToolResponse containing:
        - status: "success" or "error"
        - file_path: Path to edited file
        - replacements: Number of replacements made
        - preview: Before/after snippet of first change

    Example:
        # Replace unique string
        edit_file("src/main.py", "def old_func():", "def new_func():")

        # Replace all occurrences of a variable name
        edit_file("src/utils.py", "oldVar", "newVar", replace_all=True)

    Notes:
        - old_string must match exactly (including whitespace and indentation)
        - Use read_file first to see exact content before editing
        - File must exist (use write_file to create new files)
        - Preserve exact indentation from the source file
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
            f"Cannot edit sensitive file: {file_path}",
            "SENSITIVE_FILE"
        )

    # Resolve the full path
    target_path = config.resolve_path(file_path)

    # Validate file exists
    if not target_path.exists():
        return _error_response(
            f"File not found: {file_path}. Use write_file to create new files.",
            "FILE_NOT_FOUND"
        )

    if not target_path.is_file():
        return _error_response(
            f"Path is not a file: {file_path}",
            "NOT_A_FILE"
        )

    # Validate old_string
    if not old_string:
        return _error_response(
            "old_string cannot be empty",
            "INVALID_OLD_STRING"
        )

    # Validate strings are different
    if old_string == new_string:
        return _error_response(
            "old_string and new_string are identical - no change needed",
            "NO_CHANGE"
        )

    try:
        # Read current content
        content = target_path.read_text(encoding="utf-8")

        # Count occurrences
        count = content.count(old_string)

        if count == 0:
            # Provide helpful hint
            hint = ""
            if old_string.strip() != old_string:
                hint = " Check whitespace/indentation - they must match exactly."
            return _error_response(
                f"old_string not found in file.{hint} Use read_file to see exact content.",
                "STRING_NOT_FOUND"
            )

        if count > 1 and not replace_all:
            return _error_response(
                f"old_string appears {count} times. Set replace_all=True to replace all, "
                "or provide more context to make the match unique.",
                "MULTIPLE_MATCHES"
            )

        # Perform replacement
        new_content = content.replace(old_string, new_string)

        # Create preview (first occurrence)
        first_index = content.find(old_string)
        context_before = 50
        context_after = 50

        # Get preview of old content
        preview_start = max(0, first_index - context_before)
        preview_end = min(len(content), first_index + len(old_string) + context_after)
        old_preview = content[preview_start:preview_end]

        # Get preview of new content
        new_first_index = preview_start
        new_preview_end = min(len(new_content), preview_start + (preview_end - preview_start) - len(old_string) + len(new_string))
        new_preview = new_content[preview_start:new_preview_end]

        # Write the file
        target_path.write_text(new_content, encoding="utf-8")

        return _success_response({
            "status": "success",
            "file_path": str(target_path),
            "replacements": count,
            "message": f"Replaced {count} occurrence{'s' if count > 1 else ''} in {file_path}",
            "preview": {
                "before": f"...{old_preview}..." if preview_start > 0 else f"{old_preview}...",
                "after": f"...{new_preview}..." if preview_start > 0 else f"{new_preview}..."
            }
        })

    except UnicodeDecodeError:
        return _error_response(
            "Cannot decode file as UTF-8. File may be binary.",
            "DECODE_ERROR"
        )

    except PermissionError:
        return _error_response(
            f"Permission denied: cannot edit {file_path}",
            "PERMISSION_DENIED"
        )

    except Exception as e:
        return _error_response(
            f"Failed to edit file: {type(e).__name__}: {e}",
            "EDIT_ERROR"
        )
