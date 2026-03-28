"""评估智能体"""
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime

from .base import BaseAgent
from ..core.schema import SearchResult, TaskStatus
from ..core.state import AgentType

logger = logging.getLogger(__name__)


class EvaluatorAgent(BaseAgent):
    """评估智能体 - 负责质量评估和信息可靠性判断"""

    def __init__(self, llm=None):
        super().__init__(
            name="EvaluatorAgent",
            description="负责评估搜索结果质量和信息可靠性"
        )
        self.llm = llm
        self._reliability_rules = {
            "high_reliability": [
                "官方报告", "学术论文", "权威媒体", "政府网站",
                "年度报告", "招股说明书", "财报"
            ],
            "medium_reliability": [
                "新闻报道", "行业分析", "博客", "社交媒体"
            ],
            "low_reliability": [
                "论坛", "评论区", "未验证的信息"
            ]
        }

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行评估任务"""
        task_id = input_data.get("task_id", "")
        search_results = input_data.get("search_results", [])
        query = input_data.get("query", "")

        if not search_results:
            return self.create_response(
                status="error",
                error="没有搜索结果需要评估"
            )

        try:
            # 评估每个搜索结果
            evaluations = await self._evaluate_results(
                search_results, query
            )

            # 计算整体质量分数
            quality_score = self._calculate_quality_score(evaluations)

            # 筛选高质量结果
            high_quality_results = [
                r for r in evaluations
                if r.get("relevance_score", 0) >= 0.7
            ]

            return self.create_response(
                status="success",
                data={
                    "task_id": task_id,
                    "evaluations": evaluations,
                    "quality_score": quality_score,
                    "high_quality_count": len(high_quality_results),
                    "recommendations": self._generate_recommendations(evaluations)
                }
            )

        except Exception as e:
            logger.error(f"评估失败: {e}")
            return self.create_response(
                status="error",
                error=str(e)
            )

    def execute_sync(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """同步执行评估任务"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(self.execute(input_data))

    async def _evaluate_results(self, search_results: List[Dict[str, Any]],
                                query: str) -> List[Dict[str, Any]]:
        """评估搜索结果"""
        evaluations = []

        for result in search_results:
            # 相关性评分
            relevance = self._calculate_relevance(
                result.get("title", ""),
                result.get("snippet", ""),
                query
            )

            # 可靠性评分
            reliability = self._calculate_reliability(
                result.get("url", ""),
                result.get("source", "")
            )

            # 质量分数
            quality_score = (relevance * 0.6) + (reliability * 0.4)

            evaluations.append({
                "title": result.get("title"),
                "url": result.get("url"),
                "relevance_score": round(relevance, 2),
                "reliability_score": round(reliability, 2),
                "quality_score": round(quality_score, 2),
                "source_type": self._classify_source(result.get("url", "")),
                "needs_review": quality_score < 0.5
            })

        # 按质量分数排序
        evaluations.sort(key=lambda x: x.get("quality_score", 0), reverse=True)

        return evaluations

    def _calculate_relevance(self, title: str, snippet: str, query: str) -> float:
        """计算相关性分数"""
        query_terms = set(query.lower().split())
        text = f"{title} {snippet}".lower()

        # 计算查询词在文本中出现的比例
        matches = sum(1 for term in query_terms if term in text)
        if not query_terms:
            return 0.5

        relevance = matches / len(query_terms)

        # 标题匹配额外加分
        title_matches = sum(1 for term in query_terms if term in title.lower())
        if title_matches > 0:
            relevance = min(1.0, relevance + 0.2)

        return relevance

    def _calculate_reliability(self, url: str, source: str) -> float:
        """计算可靠性分数"""
        url_lower = url.lower()
        source_lower = source.lower() if source else ""

        # 高可靠性来源
        high_reliability_keywords = [
            ".gov", ".edu", "arxiv", "nature", "science",
            "reuters", "bloomberg", "wsj", "ft.com",
            "annual report", "10-K", "prospectus"
        ]

        # 低可靠性来源
        low_reliability_keywords = [
            "forum", "blogspot", "twitter", "reddit",
            "weibo", "baidu", "zhihu"
        ]

        for keyword in high_reliability_keywords:
            if keyword in url_lower or keyword in source_lower:
                return 0.9

        for keyword in low_reliability_keywords:
            if keyword in url_lower:
                return 0.3

        return 0.6  # 默认中等可靠性

    def _classify_source(self, url: str) -> str:
        """分类信息来源"""
        url_lower = url.lower()

        if any(kw in url_lower for kw in [".gov", ".edu"]):
            return "government/academic"
        elif any(kw in url_lower for kw in ["reuters", "bloomberg", "wsj", "ft.com"]):
            return "news agency"
        elif any(kw in url_lower for kw in ["github", "stackoverflow", "medium"]):
            return "developer"
        elif any(kw in url_lower for kw in ["forum", "reddit", "weibo"]):
            return "social"
        else:
            return "general"

    def _calculate_quality_score(self, evaluations: List[Dict[str, Any]]) -> float:
        """计算整体质量分数"""
        if not evaluations:
            return 0.0

        scores = [e.get("quality_score", 0) for e in evaluations]
        return sum(scores) / len(scores)

    def _generate_recommendations(self, evaluations: List[Dict[str, Any]]) -> List[str]:
        """生成建议"""
        recommendations = []

        low_quality = [e for e in evaluations if e.get("quality_score", 0) < 0.5]
        if low_quality:
            recommendations.append(
                f"建议排除{len(low_quality)}个低质量信息来源"
            )

        if not evaluations:
            recommendations.append("未找到足够的信息源")
        elif len(evaluations) < 5:
            recommendations.append("建议增加搜索关键词以获取更多信息")

        social_sources = [e for e in evaluations if e.get("source_type") == "social"]
        if len(social_sources) > len(evaluations) * 0.5:
            recommendations.append(
                "注意：信息主要来自社交媒体，建议补充权威来源"
            )

        return recommendations

    async def evaluate_with_llm(self, results: List[SearchResult],
                               query: str) -> Dict[str, Any]:
        """使用LLM进行深度评估"""
        if not self.llm:
            return await self._rule_based_evaluate(results, query)

        prompt = f"""请评估以下关于"{query}"的搜索结果的质量和可靠性。

搜索结果:
{self._format_results(results)}

请评估每个结果并给出:
1. 相关性评分 (0-1)
2. 可靠性评分 (0-1)
3. 简短评语
"""
        try:
            response = await self.llm.ainvoke(prompt)
            return {
                "llm_evaluation": response.content,
                "formatted": self._parse_llm_evaluation(response.content)
            }
        except Exception as e:
            logger.error(f"LLM评估失败: {e}")
            return await self._rule_based_evaluate(results, query)

    async def _rule_based_evaluate(self, results: List[SearchResult],
                                   query: str) -> Dict[str, Any]:
        """基于规则的评估"""
        return {
            "scores": [
                {
                    "relevance": self._calculate_relevance(r.title, r.snippet, query),
                    "reliability": self._calculate_reliability(r.url, r.source or "")
                }
                for r in results
            ]
        }

    def _format_results(self, results: List[SearchResult]) -> str:
        """格式化结果"""
        formatted = []
        for i, result in enumerate(results, 1):
            formatted.append(
                f"{i}. {result.title}\n"
                f"   URL: {result.url}\n"
                f"   摘要: {result.snippet}\n"
            )
        return "\n".join(formatted)

    def _parse_llm_evaluation(self, text: str) -> List[Dict[str, Any]]:
        """解析LLM评估结果"""
        # 简单解析，实际可以改进
        evaluations = []
        lines = text.split("\n")
        current_eval = {}

        for line in lines:
            if line.strip().startswith(("1.", "2.", "3.", "4.", "5.")):
                if current_eval:
                    evaluations.append(current_eval)
                current_eval = {}
            # 解析评分和评语
            # ...

        if current_eval:
            evaluations.append(current_eval)

        return evaluations