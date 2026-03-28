"""金融数据工具"""
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime
from abc import ABC, abstractmethod

from ..config.settings import settings

logger = logging.getLogger(__name__)


class FinanceProvider(ABC):
    """金融数据提供者抽象基类"""

    @abstractmethod
    async def get_stock_data(self, symbol: str) -> Dict[str, Any]:
        """获取股票数据"""
        pass

    @abstractmethod
    async def get_company_info(self, symbol: str) -> Dict[str, Any]:
        """获取公司信息"""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """获取提供者名称"""
        pass


class YahooFinanceProvider(FinanceProvider):
    """Yahoo Finance提供者"""

    def get_name(self) -> str:
        return "yahoo_finance"

    async def get_stock_data(self, symbol: str) -> Dict[str, Any]:
        """获取股票数据"""
        try:
            import yfinance
            ticker = yfinance.Ticker(symbol)
            info = ticker.info

            return {
                "symbol": symbol,
                "current_price": info.get("currentPrice"),
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "dividend_yield": info.get("dividendYield"),
                "52w_high": info.get("fiftyTwoWeekHigh"),
                "52w_low": info.get("fiftyTwoWeekLow"),
                "volume": info.get("volume"),
                "description": info.get("longBusinessDescription", "")
            }
        except ImportError:
            logger.warning("yfinance未安装")
            return self._mock_stock_data(symbol)
        except Exception as e:
            logger.warning(f"获取股票数据失败: {e}")
            return self._mock_stock_data(symbol)

    async def get_company_info(self, symbol: str) -> Dict[str, Any]:
        """获取公司信息"""
        try:
            import yfinance
            ticker = yfinance.Ticker(symbol)
            info = ticker.info

            return {
                "symbol": symbol,
                "name": info.get("shortName"),
                "industry": info.get("industry"),
                "sector": info.get("sector"),
                "employees": info.get("fullTimeEmployees"),
                "website": info.get("website"),
                "description": info.get("longBusinessDescription", "")
            }
        except Exception as e:
            logger.warning(f"获取公司信息失败: {e}")
            return self._mock_company_info(symbol)

    def _mock_stock_data(self, symbol: str) -> Dict[str, Any]:
        """模拟股票数据"""
        return {
            "symbol": symbol,
            "current_price": 100.00,
            "market_cap": 1000000000,
            "pe_ratio": 20.5,
            "dividend_yield": 2.5,
            "52w_high": 120.00,
            "52w_low": 80.00,
            "volume": 1000000,
            "description": f"{symbol}的模拟股票数据"
        }

    def _mock_company_info(self, symbol: str) -> Dict[str, Any]:
        """模拟公司信息"""
        return {
            "symbol": symbol,
            "name": f"{symbol}公司",
            "industry": "科技",
            "sector": "Technology",
            "employees": 1000,
            "website": f"https://www.{symbol}.com",
            "description": f"{symbol}是一家专注于科技创新的公司"
        }


class MockFinanceProvider(FinanceProvider):
    """模拟金融数据提供者"""

    def get_name(self) -> str:
        return "mock_finance"

    async def get_stock_data(self, symbol: str) -> Dict[str, Any]:
        """返回模拟股票数据"""
        return {
            "symbol": symbol,
            "current_price": 150.00 + hash(symbol) % 100,
            "market_cap": 50000000000 + hash(symbol) % 100000000000,
            "pe_ratio": 15.0 + (hash(symbol) % 30),
            "dividend_yield": 1.5 + (hash(symbol) % 3),
            "52w_high": 180.00,
            "52w_low": 90.00,
            "volume": 5000000 + hash(symbol) % 10000000,
            "description": f"{symbol} - 模拟股票数据"
        }

    async def get_company_info(self, symbol: str) -> Dict[str, Any]:
        """返回模拟公司信息"""
        return {
            "symbol": symbol,
            "name": f"{symbol} Holdings Inc.",
            "industry": "Technology",
            "sector": "Software",
            "employees": 5000,
            "website": f"https://www.{symbol.lower()}.com",
            "description": f"{symbol}是一家全球领先的科技公司，专注于人工智能和云计算领域。"
        }


class FinanceTool:
    """金融数据工具"""

    def __init__(self):
        self._providers: Dict[str, FinanceProvider] = {}
        self._default_provider: Optional[str] = None

    def register_provider(self, provider: FinanceProvider) -> None:
        """注册金融数据提供者"""
        self._providers[provider.get_name()] = provider
        if self._default_provider is None:
            self._default_provider = provider.get_name()
        logger.info(f"金融数据提供者已注册: {provider.get_name()}")

    async def get_stock_data(self, symbol: str, provider: str = None) -> Dict[str, Any]:
        """获取股票数据"""
        provider_name = provider or self._default_provider
        if provider_name not in self._providers:
            logger.error(f"未知的金融数据提供者: {provider_name}")
            return {}

        provider_obj = self._providers[provider_name]
        return await provider_obj.get_stock_data(symbol)

    async def get_company_info(self, symbol: str, provider: str = None) -> Dict[str, Any]:
        """获取公司信息"""
        provider_name = provider or self._default_provider
        if provider_name not in self._providers:
            logger.error(f"未知的金融数据提供者: {provider_name}")
            return {}

        provider_obj = self._providers[provider_name]
        return await provider_obj.get_company_info(symbol)

    def list_providers(self) -> List[str]:
        """列出所有提供者"""
        return list(self._providers.keys())


# 创建全局金融工具实例
finance_tool = FinanceTool()

# 默认注册模拟提供者
finance_tool.register_provider(MockFinanceProvider())