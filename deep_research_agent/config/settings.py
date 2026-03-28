"""配置文件"""
import os
from typing import Optional
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置"""

    # DeepSeek配置
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    # 搜索工具配置
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")
    duckduckgo_max_results: int = 10

    # 新闻API配置
    newsapi_key: str = os.getenv("NEWSAPI_KEY", "")

    # 应用配置
    app_name: str = "Deep Research Agent"
    app_version: str = "1.0.0"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

    # 研究配置
    max_research_depth: int = 3
    max_sources_per_task: int = 10
    default_timeout: int = 300

    # 检查点配置
    checkpoint_dir: str = "./checkpoints"

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()