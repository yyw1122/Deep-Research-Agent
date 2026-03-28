"""新闻工具"""
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime, timedelta
from abc import ABC, abstractmethod

from ..core.schema import SearchResult
from ..config.settings import settings

logger = logging.getLogger(__name__)


class NewsProvider(ABC):
    """新闻提供者抽象基类"""

    @abstractmethod
    async def get_latest_news(self, query: str = None,
                           max_results: int = 10) -> List[Dict[str, Any]]:
        """获取最新新闻"""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """获取提供者名称"""
        pass


class NewsAPIProvider(NewsProvider):
    """NewsAPI提供者"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.newsapi_key
        self.base_url = "https://newsapi.org/v2"

    def get_name(self) -> str:
        return "newsapi"

    async def get_latest_news(self, query: str = None,
                            max_results: int = 10) -> List[Dict[str, Any]]:
        """使用NewsAPI获取新闻"""
        if not self.api_key:
            logger.warning("NewsAPI密钥未配置")
            return self._mock_news(query, max_results)

        try:
            import aiohttp
            params = {
                "apiKey": self.api_key,
                "pageSize": max_results,
                "language": "en"
            }
            if query:
                params["q"] = query

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/top-headlines",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self._parse_articles(data.get("articles", []))
                    else:
                        logger.warning(f"NewsAPI错误: {response.status}")
                        return self._mock_news(query, max_results)
        except Exception as e:
            logger.warning(f"NewsAPI请求失败: {e}")
            return self._mock_news(query, max_results)

    def _parse_articles(self, articles: List[Dict]) -> List[Dict[str, Any]]:
        """解析新闻文章"""
        parsed = []
        for article in articles:
            parsed.append({
                "title": article.get("title", ""),
                "url": article.get("url", ""),
                "description": article.get("description", ""),
                "source": article.get("source", {}).get("name", ""),
                "published_at": article.get("publishedAt", ""),
                "content": article.get("content", "")
            })
        return parsed


class MockNewsProvider(NewsProvider):
    """模拟新闻提供者"""

    def get_name(self) -> str:
        return "mock_news"

    async def get_latest_news(self, query: str = None,
                            max_results: int = 10) -> List[Dict[str, Any]]:
        """返回模拟新闻"""
        return self._mock_news(query, max_results)

    def _mock_news(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """生成模拟新闻数据"""
        base_news = [
            {
                "title": f"{query}行业迎来重大突破",
                "description": f"近日，{query}领域传来重大消息，多家领先企业宣布重要技术突破..."
            },
            {
                "title": f"分析师看{query}市场前景",
                "description": f"多位行业分析师表示，{query}市场未来几年将保持高速增长..."
            },
            {
                "title": f"{query}产业链上下游整合加速",
                "description": f"随着{query}市场的快速发展，产业链上下游企业加速整合..."
            },
            {
                "title": f"资本密集布局{query}赛道",
                "description": f"近期，多家投资机构宣布投资{query}相关企业..."
            },
            {
                "title": f"{query}技术创新动态",
                "description": f"技术创新持续推动{query}行业发展，新产品新技术不断涌现..."
            }
        ]

        news = []
        for i, item in enumerate(base_news[:max_results]):
            news.append({
                "title": item["title"],
                "url": f"https://news.example.com/{query.replace(' ', '-')}-{i}",
                "description": item["description"],
                "source": "模拟新闻源",
                "published_at": (datetime.now() - timedelta(hours=i*2)).isoformat(),
                "content": item["description"]
            })

        return news


class NewsTool:
    """新闻工具"""

    def __init__(self):
        self._providers: Dict[str, NewsProvider] = {}
        self._default_provider: Optional[str] = None

    def register_provider(self, provider: NewsProvider) -> None:
        """注册新闻提供者"""
        self._providers[provider.get_name()] = provider
        if self._default_provider is None:
            self._default_provider = provider.get_name()
        logger.info(f"新闻提供者已注册: {provider.get_name()}")

    async def get_news(self, query: str = None, provider: str = None,
                      max_results: int = 10) -> List[Dict[str, Any]]:
        """获取新闻"""
        provider_name = provider or self._default_provider
        if provider_name not in self._providers:
            logger.error(f"未知的新闻提供者: {provider_name}")
            return []

        provider_obj = self._providers[provider_name]
        return await provider_obj.get_latest_news(query, max_results)

    def list_providers(self) -> List[str]:
        """列出所有提供者"""
        return list(self._providers.keys())


# 创建全局新闻工具实例
news_tool = NewsTool()

# 默认注册模拟提供者
news_tool.register_provider(MockNewsProvider())