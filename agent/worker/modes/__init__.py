# -*- coding: utf-8 -*-
"""
Worker 执行模式

提供不同的执行策略实现。
"""
# Handle both package and standalone imports
try:
    from .react_mode import ReactModeExecutor
    from .single_mode import SingleModeExecutor
    from .loop_mode import LoopModeExecutor
except ImportError:
    from react_mode import ReactModeExecutor
    from single_mode import SingleModeExecutor
    from loop_mode import LoopModeExecutor

__all__ = [
    "ReactModeExecutor",
    "SingleModeExecutor",
    "LoopModeExecutor",
]
