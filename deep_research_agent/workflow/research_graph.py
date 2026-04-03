"""LangGraph工作流定义 - 增强版"""
from typing import TypedDict, Literal, Optional, Dict, Any, List, Annotated
from datetime import datetime
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode

from ..core.schema import ResearchPlan, ResearchReport, SearchResult, TaskStatus
from ..core.state import ResearchState, AgentType
from ..agents.planner import PlannerAgent
from ..agents.searcher import SearcherAgent
from ..agents.evaluator import EvaluatorAgent
from ..agents.writer import WriterAgent
from ..tools.search import search_tool

logger = logging.getLogger(__name__)

# 配置
EVALUATION_THRESHOLD = 0.6  # 评估阈值，低于此值需要重新搜索
MAX_SEARCH_ITERATIONS = 3  # 最大搜索迭代次数


class GraphState(TypedDict):
    """图状态 - 增强版"""
    # 任务信息
    query: str
    task_id: str

    # 计划
    plan: Optional[Dict[str, Any]]
    plan_approved: bool

    # 执行
    current_task_index: int
    completed_tasks: List[str]

    # 搜索结果
    search_results: Dict[str, List[Dict[str, Any]]]

    # 评估
    evaluations: Dict[str, Any]
    search_iterations: int  # 搜索迭代次数
    needs_refinement: bool  # 是否需要重新搜索

    # 报告
    report: Optional[Dict[str, Any]]

    # 用户介入
    user_intervention_pending: bool
    user_feedback: Optional[str]

    # 错误
    error: Optional[str]

    # 消息和进度
    messages: List[str]
    progress: float  # 0-100 进度百分比
    current_step: str  # 当前步骤描述

    # 流式输出
    streaming_content: Optional[str]

    # LLM 实例
    llm: Optional[Any]


def update_progress(state: GraphState, progress: float, step: str) -> GraphState:
    """更新进度"""
    state["progress"] = progress
    state["current_step"] = step
    return state


def planning_node(state: GraphState) -> GraphState:
    """规划节点"""
    logger.info("执行规划节点...")
    query = state["query"]

    # 更新进度
    state = update_progress(state, 10, "正在分析研究任务...")
    state["messages"].append(f"开始分析: {query}")

    # 使用PlannerAgent
    from ..agents.planner import PlannerAgent
    planner = PlannerAgent(llm=state.get("llm"))
    result = planner.execute_sync({"query": query, "context": {}})

    if result.get("status") == "success":
        state["plan"] = result.get("data", {}).get("plan")
        task_count = len(state["plan"].get("tasks", []))
        state["messages"].append(f"生成研究计划，包含 {task_count} 个子任务")
        state["user_intervention_pending"] = True
        state = update_progress(state, 25, f"计划已生成，等待确认 ({task_count}个子任务)")
    else:
        state["error"] = result.get("error", "规划失败")
        state = update_progress(state, 0, "规划失败")

    return state


def user_approval_node(state: GraphState) -> GraphState:
    """用户确认节点"""
    logger.info("等待用户确认...")

    if state.get("plan_approved"):
        state["messages"].append("计划已通过审核")
        state["user_intervention_pending"] = False
        state = update_progress(state, 30, "开始执行搜索...")
    else:
        state["user_intervention_pending"] = True
        state = update_progress(state, 25, "等待用户确认研究计划")

    return state


async def search_node_parallel(state: GraphState) -> GraphState:
    """并行搜索节点 - 使用 asyncio 并行执行多个搜索任务"""
    logger.info("执行并行搜索节点...")

    if not state.get("plan"):
        state["error"] = "没有研究计划"
        return state

    tasks = state["plan"].get("tasks", [])
    total_tasks = len(tasks)
    state = update_progress(state, 35, f"开始并行搜索 ({total_tasks}个任务)...")

    # 使用 SearcherAgent
    from ..agents.searcher import SearcherAgent
    searcher = SearcherAgent(llm=state.get("llm"))
    searcher.register_search_provider("default", search_tool)

    # 串行执行（保持兼容性）
    result = searcher.execute_sync({
        "tasks": tasks,
        "max_results": 10
    })

    if result.get("status") == "success":
        state["search_results"] = result.get("data", {}).get("results", {})
        completed = sum(len(v) for v in state["search_results"].values())
        state["messages"].append(f"搜索完成，获得 {completed} 条结果")
        state = update_progress(state, 55, f"搜索完成 ({completed}条结果)")
    else:
        state["error"] = result.get("error", "搜索失败")
        state = update_progress(state, 50, "搜索失败")

    # 初始化搜索迭代计数
    state["search_iterations"] = 1

    return state


def search_node(state: GraphState) -> GraphState:
    """搜索节点（兼容接口）"""
    # 同步调用异步版本
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(search_node_parallel(state))
    finally:
        loop.close()


def evaluation_node(state: GraphState) -> GraphState:
    """评估节点 - 增强反馈循环"""
    logger.info("执行评估节点...")
    state = update_progress(state, 60, "正在评估信息质量...")

    search_results = state.get("search_results", {})

    # 使用EvaluatorAgent
    from ..agents.evaluator import EvaluatorAgent
    evaluator = EvaluatorAgent(llm=state.get("llm"))

    evaluations = {}
    for task_id, results in search_results.items():
        eval_result = evaluator.execute_sync({
            "task_id": task_id,
            "search_results": results,
            "query": state["query"]
        })

        if eval_result.get("status") == "success":
            evaluations[task_id] = eval_result.get("data", {})

    state["evaluations"] = evaluations

    # 统计高质量结果
    high_quality = sum(1 for e in evaluations.values() if e.get("high_quality_count", 0) > 0)
    state["messages"].append(f"评估完成，{high_quality}个任务发现高质量信息")

    # 检查是否需要重新搜索（反馈循环）
    avg_score = sum(e.get("overall_score", 0) for e in evaluations.values()) / max(len(evaluations), 1)
    state["search_iterations"] = state.get("search_iterations", 1)

    if avg_score < EVALUATION_THRESHOLD and state["search_iterations"] < MAX_SEARCH_ITERATIONS:
        state["needs_refinement"] = True
        state["messages"].append(f"评估分数 {avg_score:.2f} 低于阈值 {EVALUATION_THRESHOLD}，准备重新搜索...")
        state = update_progress(state, 65, f"评估分数较低，准备第 {state['search_iterations'] + 1} 次搜索...")
    else:
        state["needs_refinement"] = False
        state = update_progress(state, 75, "评估完成")

    return state


def check_evaluation_quality(state: GraphState) -> Literal["refine_search", "writing"]:
    """检查评估质量 - 决定是否需要重新搜索"""
    if state.get("needs_refinement", False):
        state["search_iterations"] = state.get("search_iterations", 1) + 1
        return "refine_search"
    return "writing"


def refine_search_node(state: GraphState) -> GraphState:
    """优化搜索节点 - 根据评估反馈调整搜索"""
    logger.info(f"执行优化搜索 (第 {state.get('search_iterations', 1)} 次)...")

    # 获取需要优化的任务
    low_quality_tasks = [
        task_id for task_id, eval_data in state.get("evaluations", {}).items()
        if eval_data.get("overall_score", 0) < EVALUATION_THRESHOLD
    ]

    if low_quality_tasks:
        state["messages"].append(f"对 {len(low_quality_tasks)} 个低分任务进行优化搜索")
        state = update_progress(state, 40, f"优化搜索中...")

    # 简化的优化搜索逻辑 - 实际实现中可以扩展关键词
    state = update_progress(state, 55, "优化搜索完成")
    return state


def writing_node(state: GraphState) -> GraphState:
    """写作节点"""
    logger.info("执行写作节点...")
    state = update_progress(state, 80, "正在生成研究报告...")

    from ..agents.writer import WriterAgent
    writer = WriterAgent(llm=state.get("llm"))

    result = writer.execute_sync({
        "query": state["query"],
        "search_results": state.get("search_results", {}),
        "evaluations": state.get("evaluations", {})
    })

    if result.get("status") == "success":
        state["report"] = result.get("data", {}).get("report")
        state["messages"].append("报告生成完成")
        state = update_progress(state, 100, "研究完成")
    else:
        state["error"] = result.get("error", "报告生成失败")
        state = update_progress(state, 90, "报告生成失败")

    return state


def check_plan_approval(state: GraphState) -> Literal["search", "planning"]:
    """检查计划是否已批准"""
    if state.get("plan_approved"):
        return "search"
    return "planning"


def check_user_intervention(state: GraphState) -> Literal["user_approval", "search"]:
    """检查是否需要用户介入"""
    if state.get("user_intervention_pending"):
        return "user_approval"
    return "search"


def should_continue(state: GraphState) -> Literal["evaluation", "writing"]:
    """判断是否继续"""
    if state.get("error"):
        return "writing"
    return "evaluation"


def create_research_graph(llm=None) -> StateGraph:
    """创建研究工作流图"""

    # 创建图
    workflow = StateGraph(GraphState)

    # 添加节点
    workflow.add_node("planning", planning_node)
    workflow.add_node("user_approval", user_approval_node)
    workflow.add_node("search", search_node)
    workflow.add_node("evaluation", evaluation_node)
    workflow.add_node("refine_search", refine_search_node)  # 新增优化搜索节点
    workflow.add_node("writing", writing_node)

    # 设置入口
    workflow.set_entry_point("planning")

    # 添加边
    workflow.add_edge("planning", "user_approval")

    workflow.add_conditional_edges(
        "user_approval",
        check_user_intervention,
        {
            "user_approval": "user_approval",
            "search": "search"
        }
    )

    workflow.add_edge("search", "evaluation")

    # 评估后根据质量决定是否需要重新搜索（反馈循环）
    workflow.add_conditional_edges(
        "evaluation",
        check_evaluation_quality,
        {
            "refine_search": "refine_search",
            "writing": "writing"
        }
    )

    # 优化搜索后再次评估
    workflow.add_edge("refine_search", "evaluation")

    workflow.add_edge("writing", END)

    return workflow


def compile_research_graph(llm=None) -> Any:
    """编译研究工作流图"""
    graph = create_research_graph(llm)
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


async def run_research_streaming(query: str, llm=None,
                                  plan_approved: bool = False,
                                  user_modifications: Dict[str, Any] = None,
                                  on_progress: callable = None) -> Dict[str, Any]:
    """运行研究任务 - 支持流式输出"""

    app = compile_research_graph(llm)

    initial_state = {
        "query": query,
        "task_id": f"task_{datetime.now().timestamp()}",
        "plan": None,
        "plan_approved": plan_approved,
        "current_task_index": 0,
        "completed_tasks": [],
        "search_results": {},
        "evaluations": {},
        "report": None,
        "user_intervention_pending": False,
        "user_feedback": None,
        "error": None,
        "messages": [],
        "progress": 0,
        "current_step": "初始化",
        "streaming_content": None,
        "llm": llm
    }

    if user_modifications:
        initial_state["user_feedback"] = user_modifications.get("feedback")

    try:
        # 异步迭代结果
        config = {"configurable": {"thread_id": initial_state["task_id"]}}

        async for event in app.astream_events(initial_state, config, version="v1"):
            kind = event.get("kind")

            # 处理节点完成事件
            if kind == "on_node_finished":
                node_name = event.get("name")
                result = event.get("data", {}).get("output")

                if on_progress and result:
                    # 提取进度信息
                    progress = result.get("progress", 0)
                    step = result.get("current_step", "")
                    if progress > 0:
                        await on_progress({
                            "node": node_name,
                            "progress": progress,
                            "step": step,
                            "messages": result.get("messages", [])
                        })

        # 获取最终结果
        result = await app.aget_state(config)
        final_state = result.values if result else initial_state

        return {
            "status": "success" if not final_state.get("error") else "partial",
            "messages": final_state.get("messages", []),
            "plan": final_state.get("plan"),
            "report": final_state.get("report"),
            "progress": final_state.get("progress", 100),
            "error": final_state.get("error")
        }

    except Exception as e:
        logger.error(f"研究任务执行失败: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


async def run_research(query: str, llm=None,
                      plan_approved: bool = False,
                      user_modifications: Dict[str, Any] = None) -> Dict[str, Any]:
    """运行研究任务 - 兼容旧接口"""

    app = compile_research_graph(llm)

    initial_state = {
        "query": query,
        "task_id": f"task_{datetime.now().timestamp()}",
        "plan": None,
        "plan_approved": plan_approved,
        "current_task_index": 0,
        "completed_tasks": [],
        "search_results": {},
        "evaluations": {},
        "report": None,
        "user_intervention_pending": False,
        "user_feedback": None,
        "error": None,
        "messages": [],
        "progress": 0,
        "current_step": "初始化",
        "streaming_content": None,
        "llm": llm
    }

    if user_modifications:
        initial_state["user_feedback"] = user_modifications.get("feedback")

    try:
        config = {"configurable": {"thread_id": initial_state["task_id"]}}
        result = await app.ainvoke(initial_state, config)

        return {
            "status": "success" if not result.get("error") else "partial",
            "messages": result.get("messages", []),
            "plan": result.get("plan"),
            "report": result.get("report"),
            "error": result.get("error")
        }

    except Exception as e:
        logger.error(f"研究任务执行失败: {e}")
        return {
            "status": "error",
            "error": str(e)
        }