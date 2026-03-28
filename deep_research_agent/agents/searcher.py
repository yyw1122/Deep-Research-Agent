"""搜索智能体"""
from typing import Dict, Any, List, Optional
import asyncio
import logging
from datetime import datetime

from .base import BaseAgent
from ..core.schema import SearchResult, SubTask, TaskStatus
from ..core.state import AgentType

logger = logging.getLogger(__name__)


class SearcherAgent(BaseAgent):
    """搜索智能体 - 负责信息收集和搜索"""

    def __init__(self, llm=None):
        super().__init__(
            name="SearcherAgent",
            description="负责调用搜索工具收集信息"
        )
        self.llm = llm
        self._search_providers = {}

    def register_search_provider(self, name: str, provider: Any) -> None:
        """注册搜索提供者"""
        self._search_providers[name] = provider
        logger.info(f"搜索提供者已注册: {name}")

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行搜索任务"""
        tasks = input_data.get("tasks", [])
        max_results = input_data.get("max_results", 10)

        if not tasks:
            return self.create_response(
                status="error",
                error="没有指定搜索任务"
            )

        try:
            # 并发搜索所有任务
            all_results = {}
            for task in tasks:
                task_id = task.get("id")
                keywords = task.get("search_keywords", [])

                if not keywords:
                    continue

                # 并行搜索关键词
                task_results = await self._search_task(
                    task_id, keywords, max_results
                )
                all_results[task_id] = task_results

            return self.create_response(
                status="success",
                data={
                    "results": {
                        task_id: [r.model_dump() for r in results]
                        for task_id, results in all_results.items()
                    },
                    "total_tasks": len(tasks),
                    "successful_tasks": len(all_results)
                }
            )

        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return self.create_response(
                status="error",
                error=str(e)
            )

    def execute_sync(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """同步执行搜索任务"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(self.execute(input_data))

    async def _search_task(self, task_id: str, keywords: List[str],
                          max_results: int) -> List[SearchResult]:
        """搜索单个任务"""
        results = []
        seen_urls = set()

        # 对每个关键词进行搜索
        for keyword in keywords:
            keyword_results = await self._search_keyword(
                keyword, max_results // len(keywords)
            )

            # 去重
            for result in keyword_results:
                if result.url not in seen_urls:
                    results.append(result)
                    seen_urls.add(result.url)

                if len(results) >= max_results:
                    break

            if len(results) >= max_results:
                break

        return results

    async def _search_keyword(self, keyword: str,
                            max_results: int) -> List[SearchResult]:
        """搜索单个关键词"""
        results = []

        # 尝试使用注册的搜索提供者
        for name, provider in self._search_providers.items():
            try:
                if hasattr(provider, 'search'):
                    search_results = await provider.search(keyword, max_results)
                    results.extend(search_results)
                elif hasattr(provider, 'invoke'):
                    # LangChain工具
                    result = await provider.ainvoke({"query": keyword})
                    if isinstance(result, list):
                        results.extend(result)
            except Exception as e:
                logger.warning(f"搜索提供者 {name} 失败: {e}")
                continue

        return results

    async def search_with_intervention(self, task: SubTask,
                                      user_keywords: List[str] = None,
                                      exclude_keywords: List[str] = None) -> Dict[str, Any]:
        """支持用户介入的搜索"""
        keywords = user_keywords or task.search_keywords

        # 过滤关键词
        if exclude_keywords:
            keywords = [k for k in keywords if k not in exclude_keywords]

        results = await self._search_task(task.id, keywords, 10)

        return {
            "task_id": task.id,
            "results": results,
            "original_keywords": task.search_keywords,
            "user_keywords": user_keywords,
            "excluded_keywords": exclude_keywords
        }

    async def extract_key_info(self, search_results: List[SearchResult],
                              query: str) -> Dict[str, Any]:
        """使用LLM从搜索结果中提取关键信息"""
        if not self.llm:
            return {
                "summary": "未使用LLM进行信息提取",
                "key_points": []
            }

        prompt = f"""从以下搜索结果中提取关于"{query}"的关键信息:

搜索结果:
{self._format_results(search_results)}

请提取:
1. 主要发现
2. 关键数据点
3. 重要趋势
"""
        try:
            response = await self.llm.ainvoke(prompt)
            return {
                "summary": response.content,
                "key_points": self._extract_key_points(response.content)
            }
        except Exception as e:
            logger.error(f"信息提取失败: {e}")
            return {"summary": "", "key_points": []}

    def _format_results(self, results: List[SearchResult]) -> str:
        """格式化搜索结果"""
        formatted = []
        for i, result in enumerate(results, 1):
            formatted.append(
                f"{i}. {result.title}\n"
                f"   URL: {result.url}\n"
                f"   内容: {result.snippet}\n"
            )
        return "\n".join(formatted)

    def _extract_key_points(self, text: str) -> List[str]:
        """提取关键点"""
        points = []
        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if line and (line.startswith("-") or line.startswith("*")):
                points.append(line.lstrip("-* ").strip())
        return points