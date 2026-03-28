"""智能体基类"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """智能体基类"""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.logger = logging.getLogger(f"agent.{name}")
        self._tools: Dict[str, Any] = {}

    @property
    def agent_type(self) -> str:
        """返回智能体类型"""
        return self.__class__.__name__.lower().replace("agent", "")

    def register_tool(self, tool_name: str, tool: Any) -> None:
        """注册工具"""
        self._tools[tool_name] = tool
        logger.info(f"工具已注册: {tool_name}")

    def get_tool(self, tool_name: str) -> Optional[Any]:
        """获取工具"""
        return self._tools.get(tool_name)

    def list_tools(self) -> List[str]:
        """列出可用工具"""
        return list(self._tools.keys())

    @abstractmethod
    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行任务"""
        pass

    async def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """验证输入数据"""
        return True

    def create_response(self, status: str, data: Any = None,
                       error: str = None) -> Dict[str, Any]:
        """创建响应"""
        response = {
            "status": status,
            "agent": self.name,
            "timestamp": datetime.now().isoformat()
        }
        if data is not None:
            response["data"] = data
        if error:
            response["error"] = error
        return response

    def log(self, level: str, message: str) -> None:
        """日志记录"""
        getattr(self.logger, level)(message)