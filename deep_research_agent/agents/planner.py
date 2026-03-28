"""规划智能体"""
from typing import Dict, Any, List
import json
import logging
from datetime import datetime

from .base import BaseAgent
from ..core.schema import SubTask, ResearchPlan, TaskStatus, TaskPriority
from ..core.state import AgentType

logger = logging.getLogger(__name__)


class PlannerAgent(BaseAgent):
    """规划智能体 - 负责任务拆解和计划生成"""

    def __init__(self, llm=None):
        super().__init__(
            name="PlannerAgent",
            description="负责分析用户意图并生成研究计划"
        )
        self.llm = llm

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行规划任务"""
        query = input_data.get("query", "")
        context = input_data.get("context", {})

        if not query:
            return self.create_response(
                status="error",
                error="缺少查询请求"
            )

        try:
            # 分析任务并生成研究计划
            plan = await self._generate_plan(query, context)
            return self.create_response(
                status="success",
                data={
                    "plan": plan.model_dump(),
                    "task_count": len(plan.tasks),
                    "requires_approval": True
                }
            )
        except Exception as e:
            logger.error(f"规划失败: {e}")
            return self.create_response(
                status="error",
                error=str(e)
            )

    def execute_sync(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """同步执行规划任务"""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self.execute(input_data))

    async def _generate_plan(self, query: str, context: Dict[str, Any]) -> ResearchPlan:
        """生成研究计划"""
        # 如果有LLM，使用LLM进行智能规划
        if self.llm:
            return await self._llm_generate_plan(query, context)

        # 否则使用基于规则的规划
        return self._rule_based_plan(query, context)

    async def _llm_generate_plan(self, query: str, context: Dict[str, Any]) -> ResearchPlan:
        """使用LLM生成计划"""
        prompt = f"""你是一个研究规划专家。请分析以下研究任务并生成详细的研究计划。

研究任务: {query}

请分析任务的各个方面，生成包含多个子任务的研究计划。计划应该:
1. 包含足够数量的子任务来全面覆盖研究主题
2. 每个子任务有明确的搜索关键词
3. 考虑任务的逻辑顺序

请以JSON格式返回计划:
{{
    "tasks": [
        {{
            "id": "task_1",
            "description": "子任务描述",
            "search_keywords": ["关键词1", "关键词2"],
            "priority": "high/medium/low"
        }}
    ],
    "execution_order": ["task_1", "task_2"]
}}
"""
        try:
            response = await self.llm.ainvoke(prompt)

            # 调试：打印原始响应
            logger.debug(f"LLM原始响应: {response}")

            # 处理不同的响应格式
            response_content = ""
            if hasattr(response, 'content'):
                response_content = response.content
            elif hasattr(response, 'text'):
                response_content = response.text
            elif isinstance(response, str):
                response_content = response
            else:
                response_content = str(response)

            logger.debug(f"响应内容: {response_content[:500]}")

            # 尝试解析JSON，如果失败则使用正则提取
            try:
                plan_data = json.loads(response_content)
            except json.JSONDecodeError:
                # 尝试从文本中提取JSON
                import re
                # 尝试多种JSON模式
                patterns = [
                    r'\{[\s\S]*\}',
                    r'\[[\s\S]*\]',
                    r'"tasks":\s*\[[\s\S]*\]',
                ]
                for pattern in patterns:
                    json_match = re.search(pattern, response_content)
                    if json_match:
                        try:
                            plan_data = json.loads(json_match.group())
                            logger.info("成功从文本中提取JSON")
                            break
                        except:
                            continue
                else:
                    raise Exception("无法解析LLM响应")

            # 转换为ResearchPlan对象
            tasks = []
            for task_data in plan_data.get("tasks", []):
                task = SubTask(
                    id=task_data.get("id", f"task_{len(tasks)+1}"),
                    description=task_data.get("description", ""),
                    status=TaskStatus.PENDING,
                    search_keywords=task_data.get("search_keywords", [])
                )
                tasks.append(task)

            plan = ResearchPlan(
                original_query=query,
                tasks=tasks,
                execution_order=plan_data.get("execution_order", [t.id for t in tasks])
            )

            return plan

        except Exception as e:
            logger.warning(f"LLM规划失败，回退到规则: {e}")
            return self._rule_based_plan(query, context)

    def _rule_based_plan(self, query: str, context: Dict[str, Any]) -> ResearchPlan:
        """基于规则的计划生成"""
        # 简单规则：根据查询生成基础子任务
        tasks = []

        # 基础研究任务
        tasks.append(SubTask(
            id="task_1",
            description=f"了解{query}的基本概念和定义",
            search_keywords=[query, "定义", "概念", "基础知识"],
            status=TaskStatus.PENDING,
            priority=TaskPriority.HIGH
        ))

        # 市场/行业分析任务
        tasks.append(SubTask(
            id="task_2",
            description=f"分析{query}的市场现状和发展趋势",
            search_keywords=[query, "市场分析", "行业报告", "发展趋势"],
            status=TaskStatus.PENDING,
            priority=TaskPriority.HIGH
        ))

        # 产业链分析任务
        tasks.append(SubTask(
            id="task_3",
            description=f"分析{query}的产业链结构和上下游关系",
            search_keywords=[query, "产业链", "上游", "下游", "供应链"],
            status=TaskStatus.PENDING,
            priority=TaskPriority.MEDIUM
        ))

        # 竞争格局任务
        tasks.append(SubTask(
            id="task_4",
            description=f"了解{query}领域的竞争格局和主要参与者",
            search_keywords=[query, "竞争格局", "主要企业", "市场份额"],
            status=TaskStatus.PENDING,
            priority=TaskPriority.MEDIUM
        ))

        # 投资/机会分析任务
        tasks.append(SubTask(
            id="task_5",
            description=f"分析{query}的投资机会和风险",
            search_keywords=[query, "投资机会", "风险分析", "前景"],
            status=TaskStatus.PENDING,
            priority=TaskPriority.LOW
        ))

        return ResearchPlan(
            original_query=query,
            tasks=tasks,
            execution_order=[t.id for t in tasks]
        )

    async def modify_plan(self, plan: ResearchPlan,
                         modifications: Dict[str, Any]) -> ResearchPlan:
        """修改研究计划"""
        # 支持用户修改计划
        if "add_tasks" in modifications:
            for task_data in modifications["add_tasks"]:
                new_task = SubTask(**task_data)
                plan.tasks.append(new_task)

        if "remove_tasks" in modifications:
            task_ids = modifications["remove_tasks"]
            plan.tasks = [t for t in plan.tasks if t.id not in task_ids]

        if "update_task" in modifications:
            for update in modifications["update_task"]:
                task_id = update.get("id")
                for task in plan.tasks:
                    if task.id == task_id:
                        task.description = update.get("description", task.description)
                        task.search_keywords = update.get("search_keywords", task.search_keywords)
                        break

        # 更新执行顺序
        plan.execution_order = [t.id for t in plan.tasks]
        plan.updated_at = datetime.now()

        return plan