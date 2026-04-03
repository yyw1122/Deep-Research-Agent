"""向量数据库存储"""
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime

from ..config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class Document:
    """文档"""
    doc_id: str
    content: str
    metadata: Dict[str, Any]
    embedding: Optional[List[float]] = None
    created_at: datetime = None


class VectorStore:
    """向量存储"""

    def __init__(self):
        self._client = None
        self._enabled = False
        self._collection = None

    async def connect(self):
        """连接向量库"""
        if not settings.vector_db_enabled:
            logger.info("向量库功能未启用")
            return

        try:
            if settings.vector_db_type == "qdrant":
                await self._connect_qdrant()
            elif settings.vector_db_type == "milvus":
                await self._connect_milvus()
            else:
                logger.warning(f"不支持的向量库类型: {settings.vector_db_type}")
        except Exception as e:
            logger.warning(f"向量库连接失败: {e}")
            self._enabled = False

    async def _connect_qdrant(self):
        """连接 Qdrant"""
        try:
            from qdrant_client import QdrantClient
            self._client = QdrantClient(url=settings.vector_db_url)

            # 创建或获取集合
            collections = self._client.get_collections().collections
            collection_names = [c.name for c in collections]

            if "research_reports" not in collection_names:
                self._client.create_collection(
                    collection_name="research_reports",
                    vectors_config={
                        "text": {
                            "size": 384,
                            "distance": "Cosine"
                        }
                    }
                )

            self._collection = "research_reports"
            self._enabled = True
            logger.info("Qdrant 向量库连接成功")
        except Exception as e:
            logger.warning(f"Qdrant 连接失败: {e}")
            self._enabled = False

    async def _connect_milvus(self):
        """连接 Milvus"""
        try:
            from pymilvus import connections, Collection
            connections.connect(
                alias="default",
                host=settings.vector_db_url.split("://")[1].split(":")[0],
                port=settings.vector_db_url.split(":")[-1]
            )
            self._enabled = True
            logger.info("Milvus 向量库连接成功")
        except Exception as e:
            logger.warning(f"Milvus 连接失败: {e}")
            self._enabled = False

    async def disconnect(self):
        """断开连接"""
        if self._client:
            if settings.vector_db_type == "qdrant":
                pass  # Qdrant 客户端不需要显式关闭
            elif settings.vector_db_type == "milvus":
                from pymilvus import connections
                connections.disconnect("default")
        self._enabled = False

    async def add_document(self, doc_id: str, content: str,
                          metadata: Dict[str, Any]) -> bool:
        """添加文档"""
        if not self._enabled:
            return False

        try:
            # 生成 embedding
            embedding = await self._generate_embedding(content)

            if settings.vector_db_type == "qdrant":
                from qdrant_client.models import PointStruct
                self._client.upsert(
                    collection_name=self._collection,
                    points=[
                        PointStruct(
                            id=doc_id,
                            vector={"text": embedding},
                            payload={
                                "content": content,
                                "metadata": metadata,
                                "created_at": datetime.now().isoformat()
                            }
                        )
                    ]
                )
                return True
            elif settings.vector_db_type == "milvus":
                # Milvus 实现
                pass

        except Exception as e:
            logger.warning(f"文档添加失败: {e}")

        return False

    async def search_similar(self, query: str, limit: int = 5,
                            tenant_id: str = None) -> List[Dict[str, Any]]:
        """搜索相似文档"""
        if not self._enabled:
            return []

        try:
            # 生成 query embedding
            embedding = await self._generate_embedding(query)

            if settings.vector_db_type == "qdrant":
                results = self._client.search(
                    collection_name=self._collection,
                    query_vector=("text", embedding),
                    limit=limit,
                    score_threshold=0.7,
                    query_filter=None  # 可添加租户过滤
                )

                return [
                    {
                        "doc_id": r.id,
                        "content": r.payload.get("content"),
                        "metadata": r.payload.get("metadata"),
                        "score": r.score
                    }
                    for r in results
                ]

        except Exception as e:
            logger.warning(f"相似搜索失败: {e}")

        return []

    async def _generate_embedding(self, text: str) -> List[float]:
        """生成 embedding"""
        try:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer('all-MiniLM-L6-v2')
            embedding = model.encode(text)
            return embedding.tolist()
        except Exception as e:
            logger.warning(f"Embedding 生成失败: {e}")
            # 返回随机 embedding
            import random
            return [random.random() for _ in range(384)]


# 全局向量存储
vector_store = VectorStore()


async def get_similar_reports(query: str, tenant_id: str = None,
                             limit: int = 5) -> List[Dict[str, Any]]:
    """获取相似研究报告"""
    return await vector_store.search_similar(query, limit, tenant_id)
