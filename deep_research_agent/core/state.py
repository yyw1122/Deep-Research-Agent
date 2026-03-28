"""状态管理"""
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .schema import (
    TaskStatus, ResearchTask, SubTask, ResearchPlan,
    ResearchReport, AgentMessage, SearchResult
)


class AgentType(str, Enum):
    """智能体类型"""
    PLANNER = "planner"
    SEARCHER = "searcher"
    EVALUATOR = "evaluator"
    WRITER = "writer"


@dataclass
class AgentState:
    """智能体状态"""
    agent_type: AgentType
    status: TaskStatus = TaskStatus.PENDING
    current_task_id: Optional[str] = None
    completed_tasks: List[str] = field(default_factory=list)
    messages: List[AgentMessage] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchState:
    """研究工作流状态"""
    # 任务信息
    query: str = ""
    task_id: str = ""

    # 计划阶段
    plan: Optional[ResearchPlan] = None
    plan_approved: bool = False

    # 执行阶段
    current_task_index: int = 0
    completed_subtasks: List[str] = field(default_factory=list)

    # 搜索结果
    search_results: Dict[str, List[SearchResult]] = field(default_factory=dict)

    # 评估结果
    evaluation_results: Dict[str, Any] = field(default_factory=dict)

    # 报告
    report: Optional[ResearchReport] = None

    # 智能体状态
    agents: Dict[AgentType, AgentState] = field(default_factory=dict)

    # 用户介入
    user_intervention_pending: bool = False
    user_feedback: Optional[str] = None

    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # 错误处理
    error: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None


class StateManager:
    """状态管理器"""

    def __init__(self):
        self._states: Dict[str, ResearchState] = {}

    def create_state(self, task_id: str, query: str) -> ResearchState:
        """创建新状态"""
        state = ResearchState(task_id=task_id, query=query)
        self._states[task_id] = state

        # 初始化智能体状态
        for agent_type in AgentType:
            state.agents[agent_type] = AgentState(agent_type=agent_type)

        return state

    def get_state(self, task_id: str) -> Optional[ResearchState]:
        """获取状态"""
        return self._states.get(task_id)

    def update_state(self, task_id: str, **kwargs) -> bool:
        """更新状态"""
        state = self._states.get(task_id)
        if not state:
            return False

        for key, value in kwargs.items():
            if hasattr(state, key):
                setattr(state, key, value)

        state.updated_at = datetime.now()
        return True

    def delete_state(self, task_id: str) -> bool:
        """删除状态"""
        if task_id in self._states:
            del self._states[task_id]
            return True
        return False

    def add_message(self, task_id: str, agent_type: AgentType,
                    message_type: str, content: Any) -> bool:
        """添加消息"""
        state = self._states.get(task_id)
        if not state:
            return False

        message = AgentMessage(
            agent_name=agent_type.value,
            message_type=message_type,
            content=content
        )
        state.agents[agent_type].messages.append(message)
        return True


# 全局状态管理器
state_manager = StateManager()