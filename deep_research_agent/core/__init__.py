"""核心模块初始化"""
from .schema import (
    TaskStatus, TaskPriority, ResearchTask, SubTask,
    ResearchPlan, SearchResult, Source, ResearchReport,
    AgentMessage, UserIntervention
)
from .state import state_manager, ResearchState, AgentType
from .checkpoint import checkpoint_manager, CheckpointManager

# 注意：Orchestrator 需要单独导入 from .orchestrator 以避免循环依赖
# from .orchestrator import Orchestrator, orchestrator

__all__ = [
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
    "state_manager",
    "ResearchState",
    "AgentType",
    "checkpoint_manager",
    "CheckpointManager",
]