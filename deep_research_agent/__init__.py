"""深度研究智能体包初始化"""
from .agents.base import BaseAgent
from .agents.planner import PlannerAgent
from .agents.searcher import SearcherAgent
from .agents.evaluator import EvaluatorAgent
from .agents.writer import WriterAgent

# 分开导入以避免循环依赖
from .core.state import state_manager, ResearchState, AgentType
from .core.checkpoint import checkpoint_manager, CheckpointManager
from .core.schema import (
    TaskStatus, TaskPriority, ResearchTask, SubTask,
    ResearchPlan, SearchResult, Source, ResearchReport,
    AgentMessage, UserIntervention
)
from .core.orchestrator import Orchestrator, orchestrator

from .config.settings import settings

from .workflow.research_graph import compile_research_graph, run_research

__version__ = "1.0.0"

__all__ = [
    # Agents
    "BaseAgent",
    "PlannerAgent",
    "SearcherAgent",
    "EvaluatorAgent",
    "WriterAgent",
    # Core
    "Orchestrator",
    "orchestrator",
    "state_manager",
    "ResearchState",
    "AgentType",
    "checkpoint_manager",
    "CheckpointManager",
    # Schema
    "TaskStatus",
    "TaskPriority",
    "ResearchTask",
    "SubTask",
    "ResearchPlan",
    "SearchResult",
    "Source",
    "ResearchReport",
    "AgentMessage",
    "UserIntervention",
    # Config
    "settings",
    # Workflow
    "compile_research_graph",
    "run_research",
]