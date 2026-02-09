# -*- coding: utf-8 -*-
"""
Shell execution tool - Cross-platform command execution.

Provides shell command execution with:
- Cross-platform support (Windows PowerShell / Linux Bash)
- Workspace-scoped execution (cwd set to workspace)
- Write permission validation
- Dangerous command blocking
- Output truncation for large results
- Timeout handling
"""

import json
import platform
import re
import subprocess
from typing import Optional, List

from agentscope.tool import ToolResponse
from agentscope.message import TextBlock

from .config import ToolConfig


# Dangerous command patterns that should be blocked
# These patterns match commands that could cause severe system damage
_DANGEROUS_PATTERNS: List[str] = [
    r"rm\s+-rf\s+/(?!\S)",       # rm -rf / (root filesystem deletion)
    r"rm\s+-rf\s+/\*",           # rm -rf /*
    r"rm\s+-rf\s+~",             # rm -rf ~ (home directory)
    r"format\s+[a-z]:",          # Windows format drive
    r"mkfs\.",                   # Linux format filesystem
    r"dd\s+if=.+of=/dev/",       # dd to device (can wipe disk)
    r":()\{.*:\|:.*\}",          # Fork bomb
    r">\s*/dev/sd[a-z]",         # Write to disk device
    r"chmod\s+777\s+/",          # Chmod 777 on root
    r"curl.*\|\s*(?:ba)?sh",     # curl piped to shell
    r"wget.*\|\s*(?:ba)?sh",     # wget piped to shell
    r"del\s+/[fqs]\s+[a-z]:\\",  # Windows delete system files
    r"rd\s+/s\s+/q\s+[a-z]:\\",  # Windows rmdir system
]


def _is_dangerous_command(command: str) -> Optional[str]:
    """
    Check if command matches dangerous patterns.

    Returns:
        Error message if dangerous, None if safe
    """
    for pattern in _DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return f"Blocked potentially dangerous command pattern"
    return None


def _success_response(data: dict) -> ToolResponse:
    """Create a success ToolResponse."""
    return ToolResponse(
        content=[TextBlock(type="text", text=json.dumps(data, ensure_ascii=False))]
    )


def _error_response(message: str, error_code: str = "SHELL_ERROR") -> ToolResponse:
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


def execute_shell(command: str, timeout: int = 120) -> ToolResponse:
    """
    Execute a shell command in the workspace directory.

    Cross-platform execution using PowerShell on Windows and Bash on Linux/macOS.
    Requires write permission to be enabled.

    Args:
        command: The shell command to execute
        timeout: Maximum execution time in seconds (default 120, max 600)

    Returns:
        ToolResponse containing:
        - status: "success" or "error"
        - stdout: Command standard output (truncated to 30000 chars)
        - stderr: Command standard error (truncated to 5000 chars)
        - exit_code: Process exit code
        - truncated: True if output was truncated

    Example:
        execute_shell("ls -la")
        execute_shell("npm install", timeout=300)

    Security Notes:
        - Command runs in workspace directory only
        - Requires write permission to prevent read-only bypass
        - Output is truncated to prevent memory issues
    """
    # Validate write permission (shell can modify files)
    try:
        config = ToolConfig.get()
    except RuntimeError as e:
        return _error_response(str(e), "CONFIG_ERROR")

    if not config.write_permission:
        return _error_response(
            "Shell execution requires write permission. "
            "Start agent with --writePermission true to enable.",
            "PERMISSION_DENIED"
        )

    # Validate command
    if not command or not command.strip():
        return _error_response("Command cannot be empty", "INVALID_COMMAND")

    # Check for dangerous commands
    danger_check = _is_dangerous_command(command)
    if danger_check:
        return _error_response(
            f"{danger_check}. This command pattern is blocked for safety.",
            "DANGEROUS_COMMAND"
        )

    # Clamp timeout
    timeout = max(1, min(timeout, 600))

    # Determine shell based on platform
    if platform.system() == "Windows":
        shell_cmd = ["powershell", "-Command", command]
    else:
        import shutil
        shell_path = shutil.which("bash") or shutil.which("sh") or "/bin/sh"
        shell_cmd = [shell_path, "-c", command]

    try:
        result = subprocess.run(
            shell_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(config.workspace),
            env=None,  # Inherit parent environment
        )

        # Truncate output to prevent memory issues
        max_stdout = 30000
        max_stderr = 5000

        stdout = result.stdout or ""
        stderr = result.stderr or ""

        truncated = False
        if len(stdout) > max_stdout:
            stdout = stdout[:max_stdout] + "\n... [output truncated]"
            truncated = True
        if len(stderr) > max_stderr:
            stderr = stderr[:max_stderr] + "\n... [stderr truncated]"
            truncated = True

        return _success_response({
            "status": "success",
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": result.returncode,
            "truncated": truncated,
            "command": command,
            "cwd": str(config.workspace)
        })

    except subprocess.TimeoutExpired:
        return _error_response(
            f"Command timed out after {timeout} seconds",
            "TIMEOUT"
        )

    except FileNotFoundError as e:
        return _error_response(
            f"Shell not found: {e}. Ensure bash/powershell is in PATH.",
            "SHELL_NOT_FOUND"
        )

    except PermissionError as e:
        return _error_response(
            f"Permission denied: {e}",
            "PERMISSION_DENIED"
        )

    except Exception as e:
        return _error_response(
            f"Shell execution failed: {type(e).__name__}: {e}",
            "EXECUTION_ERROR"
        )
