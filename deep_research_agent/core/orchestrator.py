"""核心调度器"""
import asyncio
import logging
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from enum import Enum

from .schema import (
    ResearchTask, ResearchPlan, ResearchReport,
    TaskStatus, UserIntervention
)
from .state import state_manager, ResearchState, AgentType
from .checkpoint import checkpoint_manager
from ..agents.planner import PlannerAgent
from ..agents.searcher import SearcherAgent
from ..agents.evaluator import EvaluatorAgent
from ..agents.writer import WriterAgent
from ..tools.search import search_tool

logger = logging.getLogger(__name__)


class InterventionPoint(str, Enum):
    """介入点"""
    PLAN_APPROVAL = "plan_approval"      # 计划确认点
    SEARCH_INTERVENTION = "search_intervention"  # 搜索干预点
    EVALUATION_REVIEW = "evaluation_review"      # 评估复核点
    REPORT_REVIEW = "report_review"            # 报告审阅点


class Orchestrator:
    """核心调度器 - 负责任务调度和流程控制"""

    def __init__(self, llm=None, progress_callback: Callable = None):
        self.llm = llm
        self.progress_callback = progress_callback

        # 初始化智能体
        self.planner = PlannerAgent(llm=llm)
        self.searcher = SearcherAgent(llm=llm)
        self.searcher.register_search_provider("default", search_tool)
        self.evaluator = EvaluatorAgent(llm=llm)
        self.writer = WriterAgent(llm=llm)

        # 回调函数
        self._callbacks: Dict[InterventionPoint, List[Callable]] = {
            point: [] for point in InterventionPoint
        }

        # 当前运行的任务
        self._running_tasks: Dict[str, asyncio.Task] = {}

    async def _report_progress(self, phase: str, progress: float, message: str):
        """报告进度"""
        if self.progress_callback:
            try:
                await self.progress_callback({
                    "phase": phase,
                    "progress": progress,
                    "message": message
                })
            except Exception as e:
                logger.warning(f"进度回调失败: {e}")

    def register_callback(self, point: InterventionPoint,
                         callback: Callable) -> None:
        """注册回调函数"""
        self._callbacks[point].append(callback)
        logger.info(f"已注册回调: {point.value}")

    async def trigger_callback(self, point: InterventionPoint,
                              data: Dict[str, Any]) -> Dict[str, Any]:
        """触发回调"""
        results = {}
        for callback in self._callbacks[point]:
            try:
                result = await callback(data)
                results[callback.__name__] = result
            except Exception as e:
                logger.error(f"回调执行失败: {e}")
                results[callback.__name__] = {"error": str(e)}
        return results

    async def create_research_task(self, query: str) -> str:
        """创建研究任务"""
        task_id = f"task_{datetime.now().timestamp()}"

        # 创建状态
        state_manager.create_state(task_id, query)

        logger.info(f"创建研究任务: {task_id}")
        return task_id

    async def start_research(self, task_id: str,
                            plan_approved: bool = False,
                            user_modifications: Dict[str, Any] = None) -> Dict[str, Any]:
        """开始研究任务"""
        state = state_manager.get_state(task_id)
        if not state:
            return {"status": "error", "error": "任务不存在"}

        try:
            # Phase 1: 规划
            logger.info(f"[{task_id}] 开始规划阶段")
            await self._report_progress("planning", 10, "正在分析研究任务...")
            plan_result = await self._execute_planning(task_id)

            if plan_result.get("status") != "success":
                return plan_result

            task_count = len(state.plan.tasks) if state.plan else 0
            await self._report_progress("planning", 25, f"计划已生成，包含{task_count}个子任务")

            # 触发计划确认回调
            await self.trigger_callback(InterventionPoint.PLAN_APPROVAL, {
                "task_id": task_id,
                "plan": state.plan
            })

            # 等待用户批准（如果是首次运行）
            if not plan_approved:
                state_manager.update_state(task_id,
                    user_intervention_pending=True)
                await self._report_progress("approval", 25, "等待用户确认研究计划")
                return {
                    "status": "waiting_approval",
                    "task_id": task_id,
                    "plan": state.plan.model_dump() if state.plan else None
                }

            # Phase 2: 搜索
            logger.info(f"[{task_id}] 开始搜索阶段")
            await self._report_progress("search", 30, "开始执行搜索...")
            search_result = await self._execute_search(task_id)

            if search_result.get("status") != "success":
                return search_result

            total_results = sum(len(v) for v in state.search_results.values())
            await self._report_progress("search", 55, f"搜索完成，获得{total_results}条结果")

            # Phase 3: 评估
            logger.info(f"[{task_id}] 开始评估阶段")
            await self._report_progress("evaluation", 60, "正在评估信息质量...")
            eval_result = await self._execute_evaluation(task_id)

            high_quality = sum(1 for e in state.evaluation_results.values() if e.get("high_quality_count", 0) > 0)
            await self._report_progress("evaluation", 75, f"评估完成，{high_quality}个任务发现高质量信息")

            # 触发评估复核回调
            await self.trigger_callback(InterventionPoint.EVALUATION_REVIEW, {
                "task_id": task_id,
                "evaluations": state.evaluation_results
            })

            # Phase 4: 写作
            logger.info(f"[{task_id}] 开始写作阶段")
            await self._report_progress("writing", 80, "正在生成研究报告...")
            report_result = await self._execute_writing(task_id)

            await self._report_progress("writing", 100, "研究完成")

            # 触发报告审阅回调
            await self.trigger_callback(InterventionPoint.REPORT_REVIEW, {
                "task_id": task_id,
                "report": state.report
            })

            # 保存检查点
            self._save_checkpoint(task_id)

            return {
                "status": "success",
                "task_id": task_id,
                "report": state.report.model_dump() if state.report else None,
                "messages": state_manager.get_state(task_id).agents[AgentType.WRITER].messages
            }

        except Exception as e:
            logger.error(f"研究任务执行失败: {e}")
            state_manager.update_state(task_id, error=str(e))
            await self._report_progress("error", 0, f"执行失败: {str(e)}")
            return {"status": "error", "error": str(e)}

    async def _execute_planning(self, task_id: str) -> Dict[str, Any]:
        """执行规划"""
        state = state_manager.get_state(task_id)
        query = state.query

        result = await self.planner.execute({"query": query})

        if result.get("status") == "success":
            plan_data = result.get("data", {}).get("plan")
            state.plan = ResearchPlan(**plan_data)
            state.agents[AgentType.PLANNER].status = TaskStatus.COMPLETED

            # 保存检查点
            self._save_checkpoint(task_id)

        return result

    async def _execute_search(self, task_id: str) -> Dict[str, Any]:
        """执行搜索"""
        state = state_manager.get_state(task_id)

        if not state.plan:
            return {"status": "error", "error": "没有研究计划"}

        tasks = [task.model_dump() for task in state.plan.tasks]
        result = await self.searcher.execute({
            "tasks": tasks,
            "max_results": 10
        })

        if result.get("status") == "success":
            results_data = result.get("data", {}).get("results", {})
            state.search_results = results_data
            state.agents[AgentType.SEARCHER].status = TaskStatus.COMPLETED

            # 保存检查点
            self._save_checkpoint(task_id)

        return result

    async def _execute_evaluation(self, task_id: str) -> Dict[str, Any]:
        """执行评估"""
        state = state_manager.get_state(task_id)

        evaluations = {}
        for task_id_key, results in state.search_results.items():
            result = await self.evaluator.execute({
                "task_id": task_id_key,
                "search_results": results,
                "query": state.query
            })

            if result.get("status") == "success":
                evaluations[task_id_key] = result.get("data", {})

        state.evaluation_results = evaluations
        state.agents[AgentType.EVALUATOR].status = TaskStatus.COMPLETED

        # 保存检查点
        self._save_checkpoint(task_id)

        return {"status": "success", "evaluations": evaluations}

    async def _execute_writing(self, task_id: str) -> Dict[str, Any]:
        """执行写作"""
        state = state_manager.get_state(task_id)

        result = await self.writer.execute({
            "query": state.query,
            "search_results": state.search_results,
            "evaluations": state.evaluation_results
        })

        if result.get("status") == "success":
            report_data = result.get("data", {}).get("report")
            state.report = ResearchReport(**report_data)
            state.agents[AgentType.WRITER].status = TaskStatus.COMPLETED

        return result

    async def approve_plan(self, task_id: str,
                          approved: bool,
                          modifications: Dict[str, Any] = None) -> Dict[str, Any]:
        """批准计划"""
        state = state_manager.get_state(task_id)
        if not state:
            return {"status": "error", "error": "任务不存在"}

        if not approved and modifications:
            # 应用用户修改
            state.plan = await self.planner.modify_plan(
                state.plan, modifications
            )
            logger.info(f"计划已修改: {task_id}")

        state.plan_approved = approved
        state.user_intervention_pending = False

        # 保存检查点
        self._save_checkpoint(task_id)

        # 继续执行
        return await self.start_research(task_id, plan_approved=approved)

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        state = state_manager.get_state(task_id)
        if not state:
            return None

        return {
            "task_id": task_id,
            "query": state.query,
            "plan_approved": state.plan_approved,
            "plan": state.plan.model_dump() if state.plan else None,
            "search_completed": len(state.search_results) > 0,
            "evaluation_completed": len(state.evaluation_results) > 0,
            "report_ready": state.report is not None,
            "error": state.error,
            "user_intervention_pending": state.user_intervention_pending
        }

    async def list_tasks(self) -> List[Dict[str, Any]]:
        """列出所有任务"""
        tasks = []
        # 简单实现：返回检查点中的任务
        for checkpoint in checkpoint_manager.list_checkpoints():
            task_id = checkpoint.get("task_id")
            status = await self.get_task_status(task_id)
            if status:
                tasks.append(status)
        return tasks

    def _save_checkpoint(self, task_id: str) -> None:
        """保存检查点"""
        state = state_manager.get_state(task_id)
        if not state:
            return

        # 转换为可序列化的字典
        state_dict = {
            "query": state.query,
            "task_id": state.task_id,
            "plan": state.plan.model_dump() if state.plan else None,
            "plan_approved": state.plan_approved,
            "current_task_index": state.current_task_index,
            "completed_subtasks": state.completed_subtasks,
            "search_results": state.search_results,
            "evaluation_results": state.evaluation_results,
            "report": state.report.model_dump() if state.report else None,
            "error": state.error
        }

        checkpoint_manager.save_checkpoint(task_id, state_dict)

    async def load_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """加载任务"""
        state_data = checkpoint_manager.load_checkpoint(task_id)
        if not state_data:
            return None

        # 恢复状态
        state_manager.create_state(task_id, state_data.get("query", ""))
        state = state_manager.get_state(task_id)

        if state_data.get("plan"):
            state.plan = ResearchPlan(**state_data["plan"])
        state.plan_approved = state_data.get("plan_approved", False)
        state.search_results = state_data.get("search_results", {})
        state.evaluation_results = state_data.get("evaluation_results", {})

        if state_data.get("report"):
            state.report = ResearchReport(**state_data["report"])

        return await self.get_task_status(task_id)

    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        # 取消运行中的任务
        if task_id in self._running_tasks:
            self._running_tasks[task_id].cancel()
            del self._running_tasks[task_id]

        # 删除状态和检查点
        state_manager.delete_state(task_id)
        checkpoint_manager.delete_checkpoint(task_id)

        logger.info(f"任务已取消: {task_id}")
        return True


# 全局调度器实例
orchestrator = Orchestrator()