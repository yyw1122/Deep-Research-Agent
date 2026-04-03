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

    # Redis配置
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_enabled: bool = os.getenv("REDIS_ENABLED", "true").lower() == "true"

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

    # 速率限制配置
    rate_limit_requests: int = 10
    rate_limit_window: int = 60

    # 认证配置
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24小时
    api_key_enabled: bool = os.getenv("API_KEY_ENABLED", "true").lower() == "true"

    # 向量库配置
    vector_db_enabled: bool = os.getenv("VECTOR_DB_ENABLED", "false").lower() == "true"
    vector_db_type: str = os.getenv("VECTOR_DB_TYPE", "qdrant")  # qdrant 或 milvus
    vector_db_url: str = os.getenv("VECTOR_DB_URL", "http://localhost:6333")

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()