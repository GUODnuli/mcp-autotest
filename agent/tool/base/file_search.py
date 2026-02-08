# -*- coding: utf-8 -*-
"""
File search tools - Glob pattern matching and content search.

Provides file discovery and content searching with:
- Glob pattern matching (glob_files)
- Regex content search (grep_files)
- Path validation against workspace boundary
- Result limiting and pagination
"""

import json
import re
from pathlib import Path
from typing import List, Optional

from agentscope.tool import ToolResponse
from agentscope.message import TextBlock

from .config import ToolConfig


def _success_response(data: dict) -> ToolResponse:
    """Create a success ToolResponse."""
    return ToolResponse(
        content=[TextBlock(type="text", text=json.dumps(data, ensure_ascii=False))]
    )


def _error_response(message: str, error_code: str = "SEARCH_ERROR") -> ToolResponse:
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
    """Create a plain text ToolResponse."""
    return ToolResponse(
        content=[TextBlock(type="text", text=text)]
    )


def glob_files(
    pattern: str,
    path: str = "",
    limit: int = 100
) -> ToolResponse:
    """
    Find files matching a glob pattern within the workspace.

    Uses glob pattern matching to discover files. Results are sorted
    by modification time (most recent first).

    IMPORTANT: This tool searches within the workspace directory (storage root).
    - User uploaded files are stored in: chat/{user_id}/{conversation_id}/
    - To search uploaded files, use path="chat/{user_id}/{conversation_id}"
    - The user_id and conversation_id are provided in SYSTEM CONTEXT

    Args:
        pattern: Glob pattern to match (e.g., "**/*.py", "*.yaml")
        path: Subdirectory to search in (relative to workspace).
              MUST specify this to limit search scope!
              Examples:
                - "chat/{user_id}/{conversation_id}" for uploaded files
                - "cache" for cached data
              Default: workspace root (NOT recommended, may include node_modules)
        limit: Maximum number of results (default 100, max 500)

    Returns:
        ToolResponse containing matching file paths (relative to workspace):
        ```
        chat/user123/conv456/api_spec.yaml
        chat/user123/conv456/requirements.txt
        ```

        Or JSON error on failure.

    Example:
        # Search uploaded files (RECOMMENDED)
        glob_files("*.yaml", "chat/user123/conv456")
        glob_files("**/*.json", "chat/user123/conv456")

        # Search specific directory
        glob_files("*.py", "src")

    Notes:
        - Pattern uses standard glob syntax (*, **, ?)
        - ** matches any number of directories
        - Results are relative paths from workspace root
        - ALWAYS specify path parameter to avoid searching node_modules
    """
    try:
        config = ToolConfig.get()
    except RuntimeError as e:
        return _error_response(str(e), "CONFIG_ERROR")

    # Validate and clamp limit
    limit = max(1, min(limit, 500))

    # Determine search directory
    if path:
        if not config.is_path_allowed(path):
            return _error_response(
                f"Access denied: '{path}' is outside the workspace boundary",
                "ACCESS_DENIED"
            )
        search_dir = config.resolve_path(path)
    else:
        search_dir = config.workspace

    # Validate search directory exists
    if not search_dir.exists():
        return _error_response(
            f"Directory not found: {path or 'workspace'}",
            "DIR_NOT_FOUND"
        )

    if not search_dir.is_dir():
        return _error_response(
            f"Path is not a directory: {path}",
            "NOT_A_DIR"
        )

    # Validate pattern
    if not pattern:
        return _error_response(
            "Pattern cannot be empty",
            "INVALID_PATTERN"
        )

    try:
        # Perform glob matching
        if "**" in pattern:
            # Recursive glob
            matches = list(search_dir.glob(pattern))
        else:
            # Non-recursive glob
            matches = list(search_dir.glob(pattern))

        # Filter to files only (exclude directories)
        file_matches = [m for m in matches if m.is_file()]

        # Sort by modification time (most recent first)
        file_matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        # Apply limit
        total_matches = len(file_matches)
        file_matches = file_matches[:limit]

        # Convert to relative paths
        relative_paths = []
        for match in file_matches:
            try:
                rel_path = match.relative_to(config.workspace)
                relative_paths.append(str(rel_path).replace("\\", "/"))
            except ValueError:
                # Should not happen due to prior validation, but handle gracefully
                continue

        # Format output
        if not relative_paths:
            return _text_response(f"No files matching pattern: {pattern}")

        result = "\n".join(relative_paths)

        # Add count header if truncated
        if total_matches > limit:
            result = f"[Showing {limit} of {total_matches} matches]\n" + result

        return _text_response(result)

    except Exception as e:
        return _error_response(
            f"Glob failed: {type(e).__name__}: {e}",
            "GLOB_ERROR"
        )


def grep_files(
    pattern: str,
    path: str = "",
    glob_filter: str = "",
    context_lines: int = 0,
    limit: int = 50,
    case_insensitive: bool = False
) -> ToolResponse:
    """
    Search file contents using regex pattern.

    Searches for pattern matches within files, optionally filtered by
    glob pattern. Returns matching lines with file paths and line numbers.

    Args:
        pattern: Regex pattern to search for (e.g., "def \\w+", "TODO:")
        path: Subdirectory to search in (relative to workspace, default: workspace root)
        glob_filter: Optional glob pattern to filter files (e.g., "**/*.py")
        context_lines: Number of context lines before/after match (default 0)
        limit: Maximum number of matches to return (default 50, max 200)
        case_insensitive: If True, perform case-insensitive search (default False)

    Returns:
        ToolResponse containing matches in format:
        ```
        src/main.py:42: def main():
        src/utils.py:15: def helper():
        ```

        With context lines if requested:
        ```
        src/main.py:41:     # Entry point
        src/main.py:42: def main():
        src/main.py:43:     pass
        ```

    Example:
        grep_files("TODO:", glob_filter="**/*.py")
        grep_files("function \\w+", path="src", glob_filter="*.js")
        grep_files("error", case_insensitive=True, context_lines=2)

    Notes:
        - Uses Python regex syntax
        - Binary files are automatically skipped
        - Large files (>1MB) are skipped with a warning
    """
    try:
        config = ToolConfig.get()
    except RuntimeError as e:
        return _error_response(str(e), "CONFIG_ERROR")

    # Validate and clamp parameters
    limit = max(1, min(limit, 200))
    context_lines = max(0, min(context_lines, 5))

    # Determine search directory
    if path:
        if not config.is_path_allowed(path):
            return _error_response(
                f"Access denied: '{path}' is outside the workspace boundary",
                "ACCESS_DENIED"
            )
        search_dir = config.resolve_path(path)
    else:
        search_dir = config.workspace

    # Validate search directory
    if not search_dir.exists():
        return _error_response(
            f"Directory not found: {path or 'workspace'}",
            "DIR_NOT_FOUND"
        )

    # Compile regex pattern
    try:
        flags = re.IGNORECASE if case_insensitive else 0
        regex = re.compile(pattern, flags)
    except re.error as e:
        return _error_response(
            f"Invalid regex pattern: {e}",
            "INVALID_REGEX"
        )

    # Determine files to search
    if glob_filter:
        files_to_search = list(search_dir.glob(glob_filter))
    else:
        # Search all files recursively
        files_to_search = list(search_dir.rglob("*"))

    # Filter to text files
    binary_extensions = {
        ".exe", ".dll", ".so", ".bin", ".zip", ".tar", ".gz",
        ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".mp3", ".mp4",
        ".pyc", ".pyo", ".class", ".o", ".woff", ".ttf"
    }
    files_to_search = [
        f for f in files_to_search
        if f.is_file() and f.suffix.lower() not in binary_extensions
    ]

    # Search files
    matches: List[str] = []
    files_searched = 0
    files_skipped = 0
    max_file_size = 1024 * 1024  # 1MB

    for file_path in files_to_search:
        if len(matches) >= limit:
            break

        try:
            # Skip large files
            if file_path.stat().st_size > max_file_size:
                files_skipped += 1
                continue

            files_searched += 1
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()

            # Get relative path
            try:
                rel_path = str(file_path.relative_to(config.workspace)).replace("\\", "/")
            except ValueError:
                continue

            # Search lines
            for line_num, line in enumerate(lines, start=1):
                if regex.search(line):
                    if len(matches) >= limit:
                        break

                    if context_lines > 0:
                        # Add context lines
                        start = max(0, line_num - context_lines - 1)
                        end = min(len(lines), line_num + context_lines)

                        for ctx_num in range(start, end):
                            ctx_line = lines[ctx_num]
                            marker = ">" if ctx_num == line_num - 1 else " "
                            matches.append(f"{marker}{rel_path}:{ctx_num + 1}: {ctx_line}")

                        matches.append("")  # Separator between match groups
                    else:
                        matches.append(f"{rel_path}:{line_num}: {line}")

        except (UnicodeDecodeError, PermissionError, OSError):
            # Skip problematic files silently
            continue

    # Format output
    if not matches:
        return _text_response(
            f"No matches found for pattern: {pattern}\n"
            f"(Searched {files_searched} files)"
        )

    result = "\n".join(matches)

    # Add summary header
    header_parts = [f"Found matches in {files_searched} files searched"]
    if files_skipped > 0:
        header_parts.append(f"({files_skipped} large files skipped)")
    if len(matches) >= limit:
        header_parts.append(f"[showing first {limit} matches]")

    result = f"[{' '.join(header_parts)}]\n\n" + result

    return _text_response(result)
