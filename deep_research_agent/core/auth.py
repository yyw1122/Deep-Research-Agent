"""认证模块"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from jose import JWTError, jwt
from passlib.context import CryptContext

from ..config.settings import settings

logger = logging.getLogger(__name__)

# 密码上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@dataclass
class User:
    """用户"""
    user_id: str
    username: str
    api_keys: List[str]
    tenant_id: str
    is_admin: bool = False
    created_at: datetime = None


class AuthManager:
    """认证管理器"""

    def __init__(self):
        self._users: Dict[str, User] = {}
        self._api_keys: Dict[str, str] = {}  # api_key -> user_id
        self._initialize_demo_users()

    def _initialize_demo_users(self):
        """初始化演示用户"""
        # Demo 用户
        demo_user = User(
            user_id="demo",
            username="demo",
            api_keys=["demo-api-key-12345"],
            tenant_id="tenant_demo",
            is_admin=True
        )
        self._users["demo"] = demo_user
        self._api_keys["demo-api-key-12345"] = "demo"

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        return pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        """获取密码哈希"""
        return pwd_context.hash(password)

    def create_access_token(self, data: Dict[str, Any],
                          expires_delta: Optional[timedelta] = None) -> str:
        """创建访问令牌"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)

        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(
            to_encode,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )
        return encoded_jwt

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """验证令牌"""
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm]
            )
            return payload
        except JWTError:
            return None

    def verify_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        """验证 API Key"""
        if api_key in self._api_keys:
            user_id = self._api_keys[api_key]
            user = self._users.get(user_id)
            if user:
                return {
                    "user_id": user.user_id,
                    "username": user.username,
                    "tenant_id": user.tenant_id,
                    "is_admin": user.is_admin
                }
        return None

    def create_api_key(self, user_id: str, key_name: str = "default") -> str:
        """创建 API Key"""
        import secrets
        api_key = f"dra_{secrets.token_urlsafe(32)}"

        if user_id in self._users:
            user = self._users[user_id]
            user.api_keys.append(api_key)

        self._api_keys[api_key] = user_id
        return api_key

    def get_user(self, user_id: str) -> Optional[User]:
        """获取用户"""
        return self._users.get(user_id)

    def get_user_by_api_key(self, api_key: str) -> Optional[User]:
        """通过 API Key 获取用户"""
        user_id = self._api_keys.get(api_key)
        if user_id:
            return self._users.get(user_id)
        return None


# 全局认证管理器
auth_manager = AuthManager()


async def verify_auth(request) -> Optional[Dict[str, Any]]:
    """验证认证

    支持:
    - Authorization: Bearer <token>
    - X-API-Key: <api_key>
    """
    # 检查 API Key
    api_key = request.headers.get("X-API-Key")
    if api_key:
        result = auth_manager.verify_api_key(api_key)
        if result:
            return result

    # 检查 Bearer Token
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
        result = auth_manager.verify_token(token)
        if result:
            return result

    return None


def require_auth(func):
    """装饰器：要求认证"""
    async def wrapper(request, *args, **kwargs):
        auth = await verify_auth(request)
        if not auth:
            from starlette.responses import JSONResponse
            return JSONResponse(
                status_code=401,
                content={"error": "Unauthorized", "message": "Valid authentication required"}
            )
        request.auth = auth
        return await func(request, *args, **kwargs)
    return wrapper
