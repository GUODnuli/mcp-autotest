# -*- coding: utf-8 -*-
"""
Agent 工具集

Tool architecture:
- base/: Platform capabilities (shell, file I/O, search, web) - always available
- utils.py: Legacy utilities (kept for backward compatibility)

Domain tools (doc_parser, case_generator, test_executor, report_tools) have been
moved to .testagent/skills/api_testing/tools/ and are loaded dynamically.

Usage:
    # Base tools
    from tool.base import (
        ToolConfig,
        execute_shell,
        read_file,
        write_file,
        edit_file,
        glob_files,
        grep_files,
        web_fetch,
    )

    # Legacy utilities (deprecated)
    from tool.utils import list_uploaded_files
"""

# ===== Base Tools (primary interface) =====
from .base import (
    ToolConfig,
    execute_shell,
    read_file,
    write_file,
    edit_file,
    glob_files,
    grep_files,
    web_fetch,
)

# ===== Legacy Utilities (backward compatibility) =====
from .utils import list_uploaded_files

# Export base tools as primary interface
__all__ = [
    # Configuration
    "ToolConfig",
    # Base tools
    "execute_shell",
    "read_file",
    "write_file",
    "edit_file",
    "glob_files",
    "grep_files",
    "web_fetch",
    # Legacy utilities
    "list_uploaded_files",
]
