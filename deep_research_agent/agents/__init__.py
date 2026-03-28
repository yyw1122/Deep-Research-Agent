"""智能体模块初始化"""
# 延迟导入以避免循环依赖
__all__ = [
    "BaseAgent",
    "PlannerAgent",
    "SearcherAgent",
    "EvaluatorAgent",
    "WriterAgent",
]


def __getattr__(name):
    if name == "BaseAgent":
        from .base import BaseAgent
        return BaseAgent
    elif name == "PlannerAgent":
        from .planner import PlannerAgent
        return PlannerAgent
    elif name == "SearcherAgent":
        from .searcher import SearcherAgent
        return SearcherAgent
    elif name == "EvaluatorAgent":
        from .evaluator import EvaluatorAgent
        return EvaluatorAgent
    elif name == "WriterAgent":
        from .writer import WriterAgent
        return WriterAgent
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")