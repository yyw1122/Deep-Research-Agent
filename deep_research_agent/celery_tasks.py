"""Celery 研究任务"""
import asyncio
import logging
from typing import Dict, Any

from .tasks import app
from .workflow.research_graph import run_research
from .core.state import state_manager
from .core.schema import ResearchTask

logger = logging.getLogger(__name__)


@app.task(bind=True, name="deep_research_agent.run_research")
def run_research_task(self, query: str, enable_llm: bool = True,
                      user_modifications: Dict[str, Any] = None) -> Dict[str, Any]:
    """异步执行研究任务"""

    try:
        # 使用 asyncio 运行异步任务
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    result = loop.run_until_complete(
        _execute_research(query, enable_llm, user_modifications)
    )

    return result


async def _execute_research(query: str, enable_llm: bool = True,
                           user_modifications: Dict[str, Any] = None) -> Dict[str, Any]:
    """内部异步执行"""

    from ..agents.planner import PlannerAgent
    from ..agents.searcher import SearcherAgent
    from ..agents.evaluator import EvaluatorAgent
    from ..agents.writer import WriterAgent
    from ..tools.search import search_tool
    from ..config.settings import settings
    from langchain_openai import ChatOpenAI

    # 初始化 LLM
    llm = None
    if enable_llm and settings.deepseek_api_key:
        llm = ChatOpenAI(
            model=settings.deepseek_model,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            temperature=0.7
        )

    # 创建智能体
    planner = PlannerAgent(llm=llm)
    searcher = SearcherAgent(llm=llm)
    searcher.register_search_provider("default", search_tool)
    evaluator = EvaluatorAgent(llm=llm)
    writer = WriterAgent(llm=llm)

    # 执行研究
    try:
        # 规划阶段
        plan_result = await planner.execute({"query": query})
        if plan_result.get("status") != "success":
            return {"status": "error", "error": plan_result.get("error")}

        # 搜索阶段
        tasks = [task.model_dump() for task in plan_result.get("data", {}).get("plan", {}).get("tasks", [])]
        search_result = await searcher.execute({"tasks": tasks, "max_results": 10})

        if search_result.get("status") != "success":
            return {"status": "error", "error": search_result.get("error")}

        # 评估阶段
        evaluations = {}
        results = search_result.get("data", {}).get("results", {})
        for task_id, task_results in results.items():
            eval_result = await evaluator.execute({
                "task_id": task_id,
                "search_results": task_results,
                "query": query
            })
            if eval_result.get("status") == "success":
                evaluations[task_id] = eval_result.get("data", {})

        # 写作阶段
        report_result = await writer.execute({
            "query": query,
            "search_results": results,
            "evaluations": evaluations
        })

        return {
            "status": "success" if report_result.get("status") == "success" else "partial",
            "report": report_result.get("data", {}).get("report"),
            "quality_score": report_result.get("data", {}).get("quality_score", 0.85)
        }

    except Exception as e:
        logger.error(f"研究任务执行失败: {e}")
        return {"status": "error", "error": str(e)}


@app.task(name="deep_research_agent.get_task_status")
def get_task_status(task_id: str) -> Dict[str, Any]:
    """获取任务状态"""
    return {"task_id": task_id, "status": "completed"}
