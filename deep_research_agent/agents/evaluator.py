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

            # 筛选高质量结果（提高阈值到0.6）
            high_quality_results = [
                r for r in evaluations
                if (r.get("relevance_score") or 0) >= 0.6
                and not r.get("needs_review", False)
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

            # 如果相关性太低，直接标记需要复查
            if relevance < 0.3:
                needs_review = True
            else:
                needs_review = quality_score < 0.5

            evaluations.append({
                "title": result.get("title"),
                "url": result.get("url"),
                "relevance_score": round(relevance, 2),
                "reliability_score": round(reliability, 2),
                "quality_score": round(quality_score, 2),
                "source_type": self._classify_source(result.get("url", "")),
                "needs_review": needs_review
            })

        # 按质量分数排序
        evaluations.sort(key=lambda x: x.get("quality_score", 0), reverse=True)

        return evaluations

    def _calculate_relevance(self, title: str, snippet: str, query: str) -> float:
        """计算多维度相关性分数"""
        query_lower = query.lower()
        title_lower = title.lower()
        snippet_lower = snippet.lower()

        # ============ 第一步：垃圾信息过滤 ============
        spam_patterns = [
            "vimeo", "porno", "sex", "adult", "xxx", "dating",
            "controller", "plc", "safety controller", "industrial",
            "casino", "gambling", "bitcoin", "cryptocurrency",
            "pill", "pharmacy", "medication", "weight loss",
            "escort", "dating", "meet", "hookup", "tiktok followers"
        ]

        # 检查查询本身是否包含这些关键词，避免误杀
        query_has_spam_keyword = any(p in query_lower for p in spam_patterns)

        combined_lower = f"{title_lower} {snippet_lower}"
        for pattern in spam_patterns:
            if pattern in combined_lower:
                # 如果查询本身包含此关键词，则保留
                if pattern not in query_lower:
                    return 0.0

        # ===== Step 3: Multi-dimension scoring =====
        # Check if query asks for small companies
        query_wants_small = any(kw in query_lower for kw in ["中小", "初创", "startup", "小公司", "创业", "a轮", "b轮"])

        # Infer company size from context
        inferred_size = self._infer_company_size(title, snippet)

        dimensions = {
            "location": {
                "keywords": ["hangzhou", "shanghai", "浙江", "江苏"],
                "weight": 0.2
            },
            "company_size_small": {
                "keywords": ["中小企业", "初创", "startup", "小公司", "创业公司", "a轮", "b轮", "c轮", "天使轮"] + inferred_size.get("small", []),
                "weight": 0.15
            },
            "company_size_big": {  # Negative when small is requested
                "keywords": ["阿里巴巴", "字节跳动", "腾讯", "百度", "京东", "美团", "拼多多", "网易", "小红书", "MiniMax", "月之暗面"] + inferred_size.get("big", []),
                "weight": -0.1
            },
            "company_size_inferred": {  # Inference from context
                "keywords": ["10人", "20人", "50人团队", "pre-a", "a1轮", "a2轮", "数百人"],
                "weight": 0.1
            },
            "position_type": {
                "keywords": ["ai", "人工智能", "大模型", "llm", "算法", "开发", "engineer", "研发",
                         "机器学习", "ml", "深度学习", "nlp", "搜索", "推荐"],
                "weight": 0.25
            },
            "job_type": {
                "keywords": ["实习", "intern", "校招", "应届", "毕业生", "春季招聘", "暑期实习"],
                "weight": 0.2
            },
            "general": {
                "keywords": ["招聘", "hiring", "job", "工作", "求职", "就业", "薪资", "工资", "面经", "面试"],
                "weight": 0.2
            }
        }

        total_score = 0.0
        total_weight = 0.0

        text = (title + " " + snippet).lower()

        for dim_name, dim_info in dimensions.items():
            keywords = dim_info["keywords"]
            weight = dim_info["weight"]

            # 检查标题和内容中是否匹配
            title_match = any(kw in title_lower for kw in keywords)
            content_match = any(kw in snippet_lower for kw in keywords)

            # 标题匹配得分更高
            if title_match:
                dim_score = 1.0
            elif content_match:
                dim_score = 0.7
            else:
                # 检查查询本身是否包含该维度的关��词（如果包含但内容没提到，给部分分数）
                if any(kw in query_lower for kw in keywords):
                    dim_score = 0.3
                else:
                    dim_score = 0.0

            total_score += dim_score * weight
            total_weight += weight

        # 计算综合相关性（0-1）
        if total_weight > 0:
            relevance = total_score / total_weight
        else:
            relevance = 0.0

        # 额外检查：如果查询中有具体地点要求，但结果中没有，扣分
        location_keywords = dimensions["location"]["keywords"]
        if any(loc in query_lower for loc in location_keywords):
            if not any(loc in text for loc in location_keywords):
                relevance *= 0.5  # 结果中没有提到地点，大幅降低

        return min(1.0, relevance)

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

    def _infer_company_size(self, title: str, snippet: str) -> Dict[str, List[str]]:
        """Infer company size from context"""
        text = (title + " " + snippet).lower()
        inferred = {"small": [], "big": []}

        # Small company indicators
        small_patterns = [
            "10人", "20人", "30人", "50人团队", "pre-a", "prea",
            "a轮融资", "b轮融资", "c轮融资", "天使轮",
            "初创", "startup", "创业团队", "小团队",
            " Accelerator", "孵化器", "科技园"
        ]
        for p in small_patterns:
            if p in text:
                inferred["small"].append(p)

        # Big company indicators
        big_patterns = [
            "上市", "纳斯达克", "纽交所", "市值",
            "数千人", "万人", "全球", "international",
            "总部", "headquarters", "Fortune500"
        ]
        for p in big_patterns:
            if p in text:
                inferred["big"].append(p)

        return inferred

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