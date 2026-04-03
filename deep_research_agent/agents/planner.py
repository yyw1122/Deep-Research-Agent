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
        query_lower = query.lower()

        # 检测查询类型并生成不同策略的prompt
        is_job_query = any(kw in query_lower for kw in [
            "招聘", "实习", "工作", "job", "intern", "hiring", "求职", "就业"
        ])
        is_location_specific = any(loc in query_lower for loc in ["杭州", "上海", "hangzhou", "shanghai"])

        if is_job_query:
            # 招聘/实习查询的专用策略
            locations = []
            if "杭州" in query_lower or "hangzhou" in query_lower:
                locations.append("杭州")
            if "上海" in query_lower or "shanghai" in query_lower:
                locations.append("上海")

            location_str = "、".join(locations) if locations else "杭州和上海"

            prompt = f"""你是一个研究规划专家。请为以下实习招聘研究任务生成详细的研究计划。

研究任务: {query}
目标城市: {location_str}

请生成包含以下子任务的研究计划（共5-7个任务）：
1. 搜索招聘渠道：主要实习招聘平台（实习僧、牛客网、BOSS直聘、猎聘等）
2. 按城市分别搜索：{location_str}的AI大模型实习岗位
3. 搜索具体公司/团队：各城市的AI大模型公司
4. 搜索面试经验：大模型实习的面经和流程
5. 搜索薪资待遇：实习工资范围

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

优先信任以下平台：实习僧(shixiseng.com)、牛客网(nowcoder.com)、BOSS直聘(zhipin.com)、猎聘(liepin.com)
"""
        else:
            # 通用查询策略
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
        import re

        tasks = []
        query_lower = query.lower()

        # ============ 检测查询类型 ============
        is_job_query = any(kw in query_lower for kw in [
            "招聘", "实习", "工作", "job", "intern", "hiring", "求职", "就业"
        ])
        is_location_specific = any(loc in query_lower for loc in ["杭州", "上海", "hangzhou", "shanghai"])
        is_small_company = any(sz in query_lower for sz in [
            "中小", "初创", "startup", "小公司", "创业", "A轮", "B轮", "天使"
        ])

        # ============ Extract key constraints for search keywords ============
        constraints = []
        if is_location_specific:
            if "杭州" in query_lower or "hangzhou" in query_lower:
                constraints.append("杭州")
            if "上海" in query_lower or "shanghai" in query_lower:
                constraints.append("上海")
        # Force small company constraint
        if is_small_company:
            constraints.append("中小企业")

        # ============ 根据查询类型生成不同策略 ============
        if is_job_query and is_location_specific:
            # 任务1: 搜索招聘平台 - 必须包含中小型企业约束
            task_id = len(tasks) + 1
            kw = ["AI大模型 实习 中小企业"] if is_small_company else ["AI大模型 实习"]
            tasks.append(SubTask(
                id=f"task_{task_id}",
                description="搜索AI大模型实习的招聘平台和渠道",
                search_keywords=kw,
                status=TaskStatus.PENDING,
                priority=TaskPriority.HIGH
            ))

            # 任务2: 分地点搜索 - 每个地点必须明确包含"中小企业"约束
            for loc in constraints[:2]:  # Hangzhou, Shanghai
                task_id = len(tasks) + 1
                if loc == "中小企业":
                    continue
                search_kw = [
                    f"{loc} AI大模型 实习 中小企业",
                    f"{loc} 大模型 初创公司 实习",
                    f"{loc} AI初创企业 招聘 实习生"
                ] if is_small_company else [
                    f"{loc} AI大模型 实习",
                    f"{loc} 大模型 实习 招聘"
                ]
                tasks.append(SubTask(
                    id=f"task_{task_id}",
                    description=f"搜索{loc}地区中小企业AI大模型实习",
                    search_keywords=search_kw,
                    status=TaskStatus.PENDING,
                    priority=TaskPriority.HIGH
                ))

            # 任务3: 搜索具体的公司/团队信息 - 必须包含中小企业
            for loc in constraints[:2]:
                if loc == "中小企业":
                    continue
                task_id = len(tasks) + 1
                search_kw = [
                    f"{loc} AI大模型 中小企业 招聘",
                    f"{loc} 人工智能 创业公司 实习",
                    f"{loc} A轮 B轮 AI公司 实习"
                ] if is_small_company else [
                    f"{loc} AI大模型 公司 团队",
                    f"{loc} 人工智能 创业公司"
                ]
                tasks.append(SubTask(
                    id=f"task_{task_id}",
                    description=f"搜索{loc}地区中小企业AI团队",
                    search_keywords=search_kw,
                    status=TaskStatus.PENDING,
                    priority=TaskPriority.MEDIUM
                ))

            # 任务4: 搜索面试经验和薪资信息
            task_id = len(tasks) + 1
            search_kw = [
                "AI大模型 实习 中小企业 面经",
                "大模型开发 实习 薪资 待遇",
                "算法工程师 实习 工资"
            ] if is_small_company else [
                "AI大模型 实习 面经 面试经验",
                "大模型开发 实习 薪资 待遇"
            ]
            tasks.append(SubTask(
                id=f"task_{task_id}",
                description="搜索AI大模型实习的面经和薪资信息",
                search_keywords=search_kw,
                status=TaskStatus.PENDING,
                priority=TaskPriority.MEDIUM
            ))

            # 任务5: 迂回策略 - 寻找中小公司名单（仅当搜索小公司时）
            if is_small_company:
                for loc in constraints[:2]:
                    if loc == "中小企业":
                        continue
                    task_id = len(tasks) + 1
                    # 迂回策略：先找公司列表，再搜招聘
                    tasks.append(SubTask(
                        id=f"task_{task_id}",
                        description=f"迂回策略：搜索{loc}AI初创公司/中小企业列表",
                        search_keywords=[
                            f"{loc} AI初创公司 列表",
                            f"{loc} 人工智能 创业公司 A轮 B轮",
                            f"{loc} AI科技公司 天使投资"
                        ],
                        status=TaskStatus.PENDING,
                        priority=TaskPriority.MEDIUM
                    ))

        elif is_job_query:
            # 通用招聘查询
            tasks.append(SubTask(
                id="task_1",
                description="搜索实习招聘的主要渠道",
                search_keywords=["实习招聘平台", "大学生实习", "校园招聘"],
                status=TaskStatus.PENDING,
                priority=TaskPriority.HIGH
            ))
            tasks.append(SubTask(
                id="task_2",
                description="搜索AI相关实习岗位",
                search_keywords=[query, "AI实习", "算法实习", "机器学习实习"],
                status=TaskStatus.PENDING,
                priority=TaskPriority.HIGH
            ))
            tasks.append(SubTask(
                id="task_3",
                description="搜索实习面试经验",
                search_keywords=["实习 面经", "面试经验", "求职建议"],
                status=TaskStatus.PENDING,
                priority=TaskPriority.MEDIUM
            ))

        else:
            # 基础研究任务（通用查询）
            tasks.append(SubTask(
                id="task_1",
                description=f"了解{query}的基本概念和定义",
                search_keywords=[query, "定义", "概念", "基础知识"],
                status=TaskStatus.PENDING,
                priority=TaskPriority.HIGH
            ))

            tasks.append(SubTask(
                id="task_2",
                description=f"分析{query}的市场现状和发展趋势",
                search_keywords=[query, "市场分析", "行业报告", "发展趋势"],
                status=TaskStatus.PENDING,
                priority=TaskPriority.HIGH
            ))

            tasks.append(SubTask(
                id="task_3",
                description=f"分析{query}的产业链结构和上下游关系",
                search_keywords=[query, "产业链", "上游", "下游", "供应链"],
                status=TaskStatus.PENDING,
                priority=TaskPriority.MEDIUM
            ))

            tasks.append(SubTask(
                id="task_4",
                description=f"了解{query}领域的竞争格局和主要参与者",
                search_keywords=[query, "竞争格局", "主要企业", "市场份额"],
                status=TaskStatus.PENDING,
                priority=TaskPriority.MEDIUM
            ))

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