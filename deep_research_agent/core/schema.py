"""数据模型定义"""
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    WAITING_USER_INPUT = "waiting_user_input"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskPriority(str, Enum):
    """任务优先级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ResearchTask(BaseModel):
    """研究任务模型"""
    id: str = Field(default_factory=lambda: f"task_{datetime.now().timestamp()}")
    description: str
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    parent_task_id: Optional[str] = None
    subtasks: List[str] = Field(default_factory=list)


class SubTask(BaseModel):
    """子任务模型"""
    id: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent: Optional[str] = None
    search_keywords: List[str] = Field(default_factory=list)
    search_results: List[Dict[str, Any]] = Field(default_factory=list)
    evaluation_score: Optional[float] = None
    output: Optional[str] = None
    error: Optional[str] = None


class ResearchPlan(BaseModel):
    """研究计划"""
    id: str = Field(default_factory=lambda: f"plan_{datetime.now().timestamp()}")
    original_query: str
    tasks: List[SubTask] = Field(default_factory=list)
    execution_order: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class SearchResult(BaseModel):
    """搜索结果"""
    title: str
    url: str
    snippet: str
    source: str
    published_at: Optional[datetime] = None
    relevance_score: Optional[float] = None


class Source(BaseModel):
    """信息来源"""
    url: str
    title: str
    content: str
    source_type: str  # "web", "news", "finance", "api"
    collected_at: datetime = Field(default_factory=datetime.now)
    reliability_score: Optional[float] = None


class ResearchReport(BaseModel):
    """研究报告"""
    id: str = Field(default_factory=lambda: f"report_{datetime.now().timestamp()}")
    title: str
    summary: str
    sections: List[Dict[str, Any]] = Field(default_factory=list)
    sources: List[Source] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    quality_score: Optional[float] = None


class AgentMessage(BaseModel):
    """智能体消息"""
    agent_name: str
    message_type: str  # "request", "response", "error", "status"
    content: Any
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UserIntervention(BaseModel):
    """用户介入"""
    intervention_type: str  # "approve", "modify", "reject", "add"
    original_plan_id: str
    user_feedback: str
    modified_plan: Optional[ResearchPlan] = None
    timestamp: datetime = Field(default_factory=datetime.now)