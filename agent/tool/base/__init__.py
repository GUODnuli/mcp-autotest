# -*- coding: utf-8 -*-
"""
Base tools package - Platform capabilities that are always available.

This package contains fundamental tools for:
- Shell execution (cross-platform)
- File I/O (read, write, edit)
- File search (glob, grep)
- Web fetch

All tools use ToolConfig for workspace-scoped security.
"""

from .config import ToolConfig
from .shell import execute_shell
from .file_read import read_file
from .file_write import write_file
from .file_edit import edit_file
from .file_search import glob_files, grep_files
from .web_fetch import web_fetch

__all__ = [
    "ToolConfig",
    # P0 Base Tools
    "execute_shell",
    "read_file",
    "write_file",
    "edit_file",
    # P1 Base Tools
    "glob_files",
    "grep_files",
    "web_fetch",
]
