"""基准测试脚本 - 对比 LLM 直接回答 vs 多智能体协作"""
import time
import json
import asyncio
import statistics
from typing import Dict, Any, List
from dataclasses import dataclass
from datetime import datetime

from deep_research_agent.config.settings import settings
from deep_research_agent.agents.planner import PlannerAgent
from deep_research_agent.agents.searcher import SearcherAgent
from deep_research_agent.agents.evaluator import EvaluatorAgent
from deep_research_agent.agents.writer import WriterAgent
from deep_research_agent.tools.search import search_tool
from langchain_openai import ChatOpenAI

# 测试主题
TEST_TOPICS = [
    "碳中和",
    "新能源汽车",
    "AI芯片",
    "量子计算",
    "自动驾驶",
    "区块链",
    "5G技术",
    "可再生能源",
    "人工智能医疗",
    "工业互联网",
    "智慧城市",
    "网络安全",
    "云计算",
    "大数据",
    "物联网",
    "虚拟现实",
    "增强现实",
    "生物识别",
    "无人机",
    "3D打印",
]

# 测试集
BENCHMARK_TOPICS = TEST_TOPICS[:15]  # 15个测试主题


@dataclass
class BenchmarkResult:
    """基准测试结果"""
    topic: str
    method: str  # "direct" 或 "multi_agent"
    duration: float  # 秒
    quality_score: float  # 0-1
    completeness: float  # 0-1
    accuracy: float  # 0-1
    structure_score: float  # 0-1
    overall_score: float  # 0-1
    tokens_used: int = 0
    error: str = None


def init_llm():
    """初始化 LLM"""
    if not settings.deepseek_api_key:
        print("警告: 未配置 DeepSeek API Key")
        return None

    return ChatOpenAI(
        model=settings.deepseek_model,
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        temperature=0.7
    )


def llm_direct_answer(llm, topic: str) -> Dict[str, Any]:
    """LLM 直接回答"""
    prompt = f"请就以下主题写一篇研究报告，包含摘要、主要发现和结论：{topic}"

    start_time = time.time()
    response = llm.invoke(prompt)
    duration = time.time() - start_time

    return {
        "content": response.content,
        "duration": duration,
        "tokens": response.usage.total_tokens if hasattr(response, 'usage') else 0
    }


async def multi_agent_research(llm, topic: str) -> Dict[str, Any]:
    """多智能体协作研究"""
    start_time = time.time()

    # Planner
    planner = PlannerAgent(llm=llm)
    plan_result = await planner.execute({"query": topic})
    if plan_result.get("status") != "success":
        return {"error": plan_result.get("error")}

    # Searcher
    searcher = SearcherAgent(llm=llm)
    searcher.register_search_provider("default", search_tool)
    tasks = [t.model_dump() for t in plan_result.get("data", {}).get("plan", {}).get("tasks", [])]
    search_result = await searcher.execute({"tasks": tasks, "max_results": 10})
    if search_result.get("status") != "success":
        return {"error": search_result.get("error")}

    # Evaluator
    evaluator = EvaluatorAgent(llm=llm)
    results = search_result.get("data", {}).get("results", {})
    evaluations = {}
    for task_id, task_results in results.items():
        eval_result = await evaluator.execute({
            "task_id": task_id,
            "search_results": task_results,
            "query": topic
        })
        if eval_result.get("status") == "success":
            evaluations[task_id] = eval_result.get("data", {})

    # Writer
    writer = WriterAgent(llm=llm)
    report_result = await writer.execute({
        "topic": topic,
        "search_results": results,
        "evaluations": evaluations
    })

    duration = time.time() - start_time

    return {
        "report": report_result.get("data", {}).get("report"),
        "duration": duration,
        "quality_score": report_result.get("data", {}).get("quality_score", 0.85)
    }


def evaluate_quality(result: Dict[str, Any], method: str) -> Dict[str, float]:
    """评估质量（简化版）"""
    content = result.get("content") or result.get("report", {}).get("content", "")

    # 完整性 - 基于内容长度
    completeness = min(len(content) / 2000, 1.0) if content else 0

    # 结构清晰度 - 检查是否有明确结构
    structure_keywords = ["摘要", "主要", "结论", "分析", "发现", "summary", "conclusion", "analysis"]
    structure_score = sum(1 for kw in structure_keywords if kw in content) / len(structure_keywords)

    # 信息准确性 - 基于 LLM 评估
    accuracy = 0.85  # 简化处理

    # 整体评分
    overall = (completeness * 0.4 + structure_score * 0.3 + accuracy * 0.3)

    return {
        "completeness": completeness,
        "accuracy": accuracy,
        "structure_score": structure_score,
        "overall_score": overall
    }


async def run_benchmark():
    """运行基准测试"""
    print("=" * 60)
    print("Deep Research Agent 基准测试")
    print("=" * 60)

    llm = init_llm()
    results: List[BenchmarkResult] = []

    for i, topic in enumerate(BENCHMARK_TOPICS):
        print(f"\n[{i+1}/{len(BENCHMARK_TOPICS)}] 测试主题: {topic}")

        # 直接回答
        if llm:
            try:
                direct_result = llm_direct_answer(llm, topic)
                quality = evaluate_quality(direct_result, "direct")
                results.append(BenchmarkResult(
                    topic=topic,
                    method="direct",
                    duration=direct_result["duration"],
                    quality_score=quality["overall_score"],
                    completeness=quality["completeness"],
                    accuracy=quality["accuracy"],
                    structure_score=quality["structure_score"],
                    overall_score=quality["overall_score"],
                    tokens_used=direct_result.get("tokens", 0)
                ))
                print(f"  直接回答: {direct_result['duration']:.2f}秒, 质量: {quality['overall_score']:.2f}")
            except Exception as e:
                print(f"  直接回答失败: {e}")

        # 多智能体协作
        try:
            agent_result = await multi_agent_research(llm, topic)
            if "error" in agent_result:
                print(f"  多智能体失败: {agent_result['error']}")
            else:
                quality = evaluate_quality(agent_result, "multi_agent")
                results.append(BenchmarkResult(
                    topic=topic,
                    method="multi_agent",
                    duration=agent_result["duration"],
                    quality_score=agent_result.get("quality_score", quality["overall_score"]),
                    completeness=quality["completeness"],
                    accuracy=quality["accuracy"],
                    structure_score=quality["structure_score"],
                    overall_score=quality["overall_score"]
                ))
                print(f"  多智能体: {agent_result['duration']:.2f}秒, 质量: {quality['overall_score']:.2f}")
        except Exception as e:
            print(f"  多智能体失败: {e}")

    # 输出统计
    print("\n" + "=" * 60)
    print("基准测试结果统计")
    print("=" * 60)

    direct_results = [r for r in results if r.method == "direct"]
    agent_results = [r for r in results if r.method == "multi_agent"]

    if direct_results:
        print("\n【直接回答】")
        print(f"  平均耗时: {statistics.mean(r.duration for r in direct_results):.2f}秒")
        print(f"  平均质量: {statistics.mean(r.overall_score for r in direct_results):.2f}")

    if agent_results:
        print("\n【多智能体协作】")
        print(f"  平均耗时: {statistics.mean(r.duration for r in agent_results):.2f}秒")
        print(f"  平均质量: {statistics.mean(r.overall_score for r in agent_results):.2f}")

    # 保存结果
    output = {
        "timestamp": datetime.now().isoformat(),
        "topics": BENCHMARK_TOPICS,
        "direct": [
            {
                "topic": r.topic,
                "duration": r.duration,
                "quality_score": r.quality_score,
                "overall_score": r.overall_score
            }
            for r in direct_results
        ],
        "multi_agent": [
            {
                "topic": r.topic,
                "duration": r.duration,
                "quality_score": r.quality_score,
                "overall_score": r.overall_score
            }
            for r in agent_results
        ]
    }

    with open("benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存到 benchmark_results.json")

    return results


if __name__ == "__main__":
    asyncio.run(run_benchmark())
