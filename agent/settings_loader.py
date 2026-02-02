# -*- coding: utf-8 -*-
"""
设置加载模块

从 .testagent/settings.json 加载项目配置。
搜索顺序：显式路径 → PROJECT_ROOT/.testagent/settings.json → 空默认值
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_SETTINGS: dict = {
    "mcpServers": {},
    "toolDisplay": {"names": {}, "hidden": []},
    "testEngine": {},
    "storage": {},
    "vectorDb": {},
}


def load_settings(path: str | None = None) -> dict:
    """
    加载 .testagent/settings.json 配置。

    Args:
        path: 显式配置文件路径。为 None 时自动搜索项目根目录。

    Returns:
        配置字典。解析失败时返回空默认值。
    """
    if path:
        settings_path = Path(path)
    else:
        project_root = Path(__file__).parent.parent
        settings_path = project_root / ".testagent" / "settings.json"

    if not settings_path.exists():
        logger.info("Settings file not found at %s, using defaults", settings_path)
        return {**_DEFAULT_SETTINGS}

    try:
        text = settings_path.read_text(encoding="utf-8")
        data = json.loads(text)
        logger.info("Loaded settings from %s", settings_path)
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to parse settings at %s: %s, using defaults", settings_path, exc)
        return {**_DEFAULT_SETTINGS}
