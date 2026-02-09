# -*- coding: utf-8 -*-
"""
Worker 加载器

从 .testagent/agents/*.md 加载 Worker 角色定义。
解析 YAML Frontmatter 获取配置，Markdown 内容作为系统提示词。
"""
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Literal, Optional, Any

import yaml

logger = logging.getLogger(__name__)

ExecutionMode = Literal["react", "single", "loop"]


@dataclass
class WorkerConfig:
    """Worker 配置定义"""

    # 基本信息
    name: str
    description: str
    system_prompt: str

    # 工具配置
    tools: List[str] = field(default_factory=list)

    # 模型配置
    model: Optional[str] = None  # 继承 Coordinator 的模型配置

    # 执行模式
    mode: ExecutionMode = "react"
    max_iterations: int = 10
    timeout: int = 300  # 秒

    # 元数据
    source_path: Optional[Path] = None
    tags: List[str] = field(default_factory=list)

    # 扩展配置 (支持自定义字段)
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "tools": self.tools,
            "model": self.model,
            "mode": self.mode,
            "max_iterations": self.max_iterations,
            "timeout": self.timeout,
            "tags": self.tags,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkerConfig":
        """从字典创建实例"""
        known_keys = {
            "name", "description", "system_prompt", "tools", "model",
            "mode", "max_iterations", "timeout", "tags", "source_path"
        }
        extra = {k: v for k, v in data.items() if k not in known_keys}

        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            system_prompt=data.get("system_prompt", ""),
            tools=data.get("tools", []),
            model=data.get("model"),
            mode=data.get("mode", "react"),
            max_iterations=data.get("max_iterations", 10),
            timeout=data.get("timeout", 300),
            tags=data.get("tags", []),
            source_path=data.get("source_path"),
            extra=extra,
        )


class WorkerLoader:
    """
    Worker 加载器

    从指定目录加载 Worker 定义文件 (*.md)，解析 YAML Frontmatter 和 Markdown 内容。
    """

    def __init__(self, agents_dir: Path):
        """
        初始化 Worker 加载器

        Args:
            agents_dir: Worker 定义文件所在目录 (通常是 .testagent/agents/)
        """
        self.agents_dir = Path(agents_dir)
        self._workers: Dict[str, WorkerConfig] = {}
        self._loaded = False

    def load(self, force_reload: bool = False) -> Dict[str, WorkerConfig]:
        """
        加载所有 Worker 定义

        Args:
            force_reload: 是否强制重新加载

        Returns:
            Worker 名称到配置的映射
        """
        if self._loaded and not force_reload:
            return self._workers

        self._workers = {}

        if not self.agents_dir.exists():
            logger.warning("Agents directory not found: %s", self.agents_dir)
            return self._workers

        for md_file in self.agents_dir.glob("*.md"):
            try:
                config = self._parse_worker_file(md_file)
                if config:
                    self._workers[config.name] = config
                    logger.info("Loaded worker: %s from %s", config.name, md_file.name)
            except Exception as exc:
                logger.warning("Failed to load worker from %s: %s", md_file, exc)

        self._loaded = True
        logger.info("Loaded %d workers from %s", len(self._workers), self.agents_dir)
        return self._workers

    def get_worker(self, name: str) -> Optional[WorkerConfig]:
        """
        获取指定名称的 Worker 配置

        Args:
            name: Worker 名称

        Returns:
            Worker 配置，不存在返回 None
        """
        if not self._loaded:
            self.load()
        return self._workers.get(name)

    def list_workers(self) -> List[str]:
        """
        列出所有已加载的 Worker 名称

        Returns:
            Worker 名称列表
        """
        if not self._loaded:
            self.load()
        return list(self._workers.keys())

    def get_worker_summary(self) -> List[Dict[str, str]]:
        """
        获取所有 Worker 的摘要信息（供 Coordinator 选择使用）

        Returns:
            包含 name, description, tools, mode 的摘要列表
        """
        if not self._loaded:
            self.load()

        return [
            {
                "name": config.name,
                "description": config.description,
                "tools": config.tools,
                "mode": config.mode,
            }
            for config in self._workers.values()
        ]

    def _parse_worker_file(self, file_path: Path) -> Optional[WorkerConfig]:
        """
        解析 Worker 定义文件

        文件格式：
        ---
        name: worker_name
        description: Worker description
        tools: [tool1, tool2]
        model: qwen3-max
        mode: react
        max_iterations: 10
        timeout: 300
        ---

        # System Prompt
        ...

        Args:
            file_path: Worker 定义文件路径

        Returns:
            WorkerConfig 实例，解析失败返回 None
        """
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to read worker file %s: %s", file_path, exc)
            return None

        # 解析 YAML Frontmatter
        frontmatter, body = self._extract_frontmatter(content)
        if not frontmatter:
            logger.warning("No frontmatter found in %s", file_path)
            return None

        # 解析 YAML
        try:
            metadata = yaml.safe_load(frontmatter) or {}
        except yaml.YAMLError as exc:
            logger.warning("Invalid YAML in %s: %s", file_path, exc)
            return None

        # 必需字段
        name = metadata.get("name")
        if not name:
            # 使用文件名作为后备
            name = file_path.stem

        description = metadata.get("description", "")

        # 工具列表（支持逗号分隔字符串或列表）
        tools_raw = metadata.get("tools", [])
        if isinstance(tools_raw, str):
            tools = [t.strip() for t in tools_raw.split(",") if t.strip()]
        elif isinstance(tools_raw, list):
            tools = [str(t).strip() for t in tools_raw]
        else:
            tools = []

        # 执行模式
        mode = metadata.get("mode", "react")
        if mode not in ("react", "single", "loop"):
            logger.warning("Invalid mode '%s' in %s, using 'react'", mode, file_path)
            mode = "react"

        # 警告: single 模式下声明的工具不会被使用
        if mode == "single" and tools:
            logger.warning(
                "Worker '%s' declares tools %s but uses mode='single'. "
                "Tools are only available in 'react' mode. "
                "Change to mode='react' if tool usage is needed.",
                metadata.get("name", file_path.stem), tools,
            )

        # 其他配置
        model = metadata.get("model")
        max_iterations = int(metadata.get("max_iterations", 10))
        timeout = int(metadata.get("timeout", 300))
        tags = metadata.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]

        # 系统提示词（Markdown 正文）
        system_prompt = body.strip()

        # 收集扩展字段
        known_keys = {
            "name", "description", "tools", "model", "mode",
            "max_iterations", "timeout", "tags"
        }
        extra = {k: v for k, v in metadata.items() if k not in known_keys}

        return WorkerConfig(
            name=name,
            description=description,
            system_prompt=system_prompt,
            tools=tools,
            model=model,
            mode=mode,
            max_iterations=max_iterations,
            timeout=timeout,
            tags=tags,
            source_path=file_path,
            extra=extra,
        )

    def _extract_frontmatter(self, content: str) -> tuple[str, str]:
        """
        提取 YAML Frontmatter 和 Markdown 正文

        Args:
            content: 文件完整内容

        Returns:
            (frontmatter, body) 元组
        """
        # 匹配 --- 之间的 YAML 内容
        match = re.match(r'^---\s*\n(.*?)\n---\s*\n?(.*)', content, re.DOTALL)
        if match:
            return match.group(1), match.group(2)
        return "", content
