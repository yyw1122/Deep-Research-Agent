"""UI模块初始化"""
from .cli import CLI, run_cli
from .web import app

__all__ = ["CLI", "run_cli", "app"]