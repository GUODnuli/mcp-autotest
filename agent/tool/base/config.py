# -*- coding: utf-8 -*-
"""
ToolConfig - Workspace-scoped security configuration for base tools.

Provides path validation and permission checking for all file operations.
Implements immutable singleton pattern for consistent security context.
"""

from __future__ import annotations

import fnmatch
import threading
from pathlib import Path
from typing import List

# Module-level singleton instance with thread safety
_instance: ToolConfig | None = None
_lock = threading.Lock()

# Sensitive file patterns that should never be written to
# Patterns are matched against both the filename and full path
_SENSITIVE_PATTERNS: List[str] = [
    # Environment files
    ".env",
    ".env.*",
    # Git config
    ".git/config",
    # Credentials and secrets (match filename directly)
    "credentials*",
    "secrets*",
    "password*",
    "token*",
    # SSH keys
    "id_rsa*",
    "id_ed25519*",
    "id_dsa*",
    "id_ecdsa*",
    "authorized_keys",
    "known_hosts",
    # Certificates and keys (match extension)
    "*.pem",
    "*.key",
    "*.pfx",
    "*.p12",
    "*.crt",
    # Cloud provider configs (match filename)
    "kubeconfig",
    # Package manager tokens (match filename)
    ".netrc",
    ".npmrc",
    ".pypirc",
    # Config files that often contain secrets
    "config.json",
    # Database files
    "*.sqlite",
    "*.sqlite3",
    "*.db",
]


class ToolConfig:
    """
    Immutable configuration for workspace-scoped tool security.

    Provides:
    - Workspace boundary enforcement
    - Path validation for read/write operations
    - Sensitive file pattern detection
    - Cross-platform path resolution

    Usage:
        # Initialize once at startup
        ToolConfig.init(workspace="/path/to/project", write_permission=True)

        # Use throughout the application
        config = ToolConfig.get()
        if config.is_write_allowed(file_path):
            # Safe to write
    """

    __slots__ = ('_workspace', '_write_permission', '_allowed_paths')

    def __init__(self, workspace: Path, write_permission: bool):
        """
        Internal constructor. Use ToolConfig.init() to create instance.

        Args:
            workspace: Resolved absolute path to workspace root
            write_permission: Whether write operations are allowed
        """
        object.__setattr__(self, '_workspace', workspace.resolve())
        object.__setattr__(self, '_write_permission', write_permission)
        object.__setattr__(self, '_allowed_paths', [workspace.resolve()])

    def __setattr__(self, name: str, value) -> None:
        """Prevent attribute modification after initialization."""
        raise AttributeError("ToolConfig is immutable")

    def __delattr__(self, name: str) -> None:
        """Prevent attribute deletion."""
        raise AttributeError("ToolConfig is immutable")

    @staticmethod
    def init(workspace: str | Path, write_permission: bool = False) -> ToolConfig:
        """
        Initialize the singleton ToolConfig instance.

        Should be called once at application startup before any tools are used.
        Thread-safe implementation using locks.

        Args:
            workspace: Path to workspace root directory (sandbox boundary)
            write_permission: Whether file write operations are allowed

        Returns:
            The initialized ToolConfig instance

        Raises:
            RuntimeError: If ToolConfig is already initialized
            ValueError: If workspace path is invalid
        """
        global _instance
        with _lock:
            if _instance is not None:
                raise RuntimeError("ToolConfig already initialized")

            workspace_path = Path(workspace)
            if not workspace_path.exists():
                raise ValueError(f"Workspace path does not exist: {workspace}")
            if not workspace_path.is_dir():
                raise ValueError(f"Workspace path is not a directory: {workspace}")

            _instance = object.__new__(ToolConfig)
            object.__setattr__(_instance, '_workspace', workspace_path.resolve())
            object.__setattr__(_instance, '_write_permission', write_permission)
            object.__setattr__(_instance, '_allowed_paths', [workspace_path.resolve()])
            return _instance

    @staticmethod
    def get() -> ToolConfig:
        """
        Get the singleton ToolConfig instance.

        Thread-safe read (no lock needed for reading after initialization).

        Returns:
            The ToolConfig instance

        Raises:
            RuntimeError: If ToolConfig has not been initialized
        """
        if _instance is None:
            raise RuntimeError("ToolConfig not initialized - call init() first")
        return _instance

    @staticmethod
    def reset() -> None:
        """
        Reset the singleton instance (for testing purposes only).

        WARNING: This should only be used in test fixtures.
        Thread-safe implementation using locks.
        """
        global _instance
        with _lock:
            _instance = None

    @property
    def workspace(self) -> Path:
        """Get the workspace root path."""
        return self._workspace

    @property
    def write_permission(self) -> bool:
        """Check if write permission is enabled."""
        return self._write_permission

    @property
    def allowed_paths(self) -> List[Path]:
        """Get list of allowed paths (includes workspace and any additional paths)."""
        return list(self._allowed_paths)

    def add_allowed_path(self, path: str | Path) -> None:
        """
        Add an additional allowed path (e.g., for temp directories).

        Note: This mutates the internal list but doesn't change immutable attributes.

        Args:
            path: Path to allow access to
        """
        resolved = Path(path).resolve()
        if resolved not in self._allowed_paths:
            self._allowed_paths.append(resolved)

    def is_path_allowed(self, target: str | Path) -> bool:
        """
        Check if a path is within the allowed boundaries.

        Resolves the path and verifies it's under the workspace or other allowed paths.

        Args:
            target: Path to check (can be relative or absolute)

        Returns:
            True if path is allowed, False otherwise
        """
        try:
            # Resolve the target path
            target_path = Path(target)
            if not target_path.is_absolute():
                target_path = (self._workspace / target_path).resolve()
            else:
                target_path = target_path.resolve()

            # Check against all allowed paths
            for allowed in self._allowed_paths:
                try:
                    target_path.relative_to(allowed)
                    return True
                except ValueError:
                    continue

            return False
        except Exception:
            return False

    def is_write_allowed(self, target: str | Path) -> bool:
        """
        Check if writing to a path is allowed.

        Requires both write_permission to be enabled AND the path to be within bounds.

        Args:
            target: Path to check

        Returns:
            True if write is allowed, False otherwise
        """
        if not self._write_permission:
            return False
        return self.is_path_allowed(target)

    def is_sensitive(self, target: str | Path) -> bool:
        """
        Check if a path matches sensitive file patterns.

        Sensitive files (like .env, credentials, keys) should not be written to
        even if write permission is enabled.

        Args:
            target: Path to check

        Returns:
            True if path is sensitive, False otherwise
        """
        try:
            target_path = Path(target)
            # Get the path as string for pattern matching
            path_str = str(target_path)
            name = target_path.name

            for pattern in _SENSITIVE_PATTERNS:
                # Check if pattern matches the filename or full path
                if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(path_str, pattern):
                    return True
                # Also check with forward slashes for cross-platform
                if fnmatch.fnmatch(path_str.replace("\\", "/"), pattern):
                    return True

            return False
        except Exception:
            # If we can't parse the path, treat it as potentially sensitive
            return True

    def resolve_path(self, target: str | Path) -> Path:
        """
        Resolve a path relative to the workspace.

        Args:
            target: Path to resolve (relative paths are relative to workspace)

        Returns:
            Resolved absolute path
        """
        target_path = Path(target)
        if not target_path.is_absolute():
            return (self._workspace / target_path).resolve()
        return target_path.resolve()
