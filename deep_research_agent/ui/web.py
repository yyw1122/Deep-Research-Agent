"""FastAPI Web界面 - 增强版"""
import asyncio
import logging
import json
import time
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request, Header
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from ..core.orchestrator import orchestrator, InterventionPoint
from ..core.schema import ResearchPlan, ResearchReport
from ..core.cache import cache_manager
from ..core.metrics import metrics_endpoint, request_counter, request_duration
from ..core.rate_limit import check_api_rate_limit
from ..core.auth import verify_auth, auth_manager
from ..config.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info("正在启动 Deep Research Agent...")
    await cache_manager.connect()
    logger.info("应用启动完成")
    yield
    # 关闭时
    await cache_manager.disconnect()
    logger.info("应用已关闭")


app = FastAPI(
    title="深度研究智能体",
    description="基于LangGraph的多智能体深度研究系统",
    version="1.1.0",
    lifespan=lifespan
)


# ====== 中间件 ======

class RateLimitMiddleware(BaseHTTPMiddleware):
    """速率限制中间件"""

    async def dispatch(self, request: Request, call_next):
        # 跳过健康检查和指标端点
        if request.url.path in ["/health", "/metrics", "/docs", "/openapi.json"]:
            return await call_next(request)

        # 获取客户端标识
        client_id = request.client.host if request.client else "unknown"

        # 检查速率限制
        allowed, limit_info = await check_api_rate_limit(client_id)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": limit_info.get("retry_after", 60)
                }
            )

        # 记录请求
        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time

        # 更新指标
        request_counter.labels(
            method=request.method,
            endpoint=request.url.path,
            status=response.status_code
        ).inc()
        request_duration.labels(
            method=request.method,
            endpoint=request.url.path
        ).observe(duration)

        return response


app.add_middleware(RateLimitMiddleware)


# ==================== 数据模型 ====================

class ResearchRequest(BaseModel):
    query: str
    enable_llm: bool = False


class PlanApprovalRequest(BaseModel):
    task_id: str
    approved: bool
    modifications: Optional[Dict[str, Any]] = None


class ReportModificationRequest(BaseModel):
    task_id: str
    modifications: Dict[str, Any]


# ==================== WebSocket连接管理 ====================

class ConnectionManager:
    """WebSocket连接管理器"""

    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, task_id: str, websocket: WebSocket):
        await websocket.accept()
        if task_id not in self.active_connections:
            self.active_connections[task_id] = []
        self.active_connections[task_id].append(websocket)
        logger.info(f"WebSocket连接: {task_id}")

    def disconnect(self, task_id: str, websocket: WebSocket):
        if task_id in self.active_connections:
            self.active_connections[task_id].remove(websocket)
        logger.info(f"WebSocket断开: {task_id}")

    async def send_message(self, task_id: str, message: dict):
        if task_id in self.active_connections:
            for connection in self.active_connections[task_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"发送消息失败: {e}")

    async def broadcast(self, message: dict):
        """广播消息到所有连接"""
        for task_id, connections in self.active_connections.items():
            for connection in connections:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass


manager = ConnectionManager()


# ==================== 回调函数 ====================

async def ws_progress_callback(data: dict) -> dict:
    """WebSocket进度回调"""
    task_id = data.get("task_id", "global")
    await manager.send_message(task_id, {
        "type": "progress",
        "phase": data.get("phase", ""),
        "progress": data.get("progress", 0),
        "message": data.get("message", "")
    })
    return {}


async def ws_plan_callback(data: dict) -> dict:
    """WebSocket计划回调"""
    task_id = data.get("task_id")
    plan = data.get("plan")
    if plan:
        await manager.send_message(task_id, {
            "type": "plan_ready",
            "plan": plan.model_dump() if hasattr(plan, 'model_dump') else plan
        })
    return {}


async def ws_report_callback(data: dict) -> dict:
    """WebSocket报告回调"""
    task_id = data.get("task_id")
    report = data.get("report")
    if report:
        await manager.send_message(task_id, {
            "type": "report_ready",
            "report": report.model_dump() if hasattr(report, 'model_dump') else report
        })
    return {}


# 注册回调
@app.on_event("startup")
async def startup():
    """启动时注册回调"""
    orchestrator.register_callback(InterventionPoint.PLAN_APPROVAL, ws_plan_callback)
    orchestrator.register_callback(InterventionPoint.REPORT_REVIEW, ws_report_callback)


# ==================== API路由 ====================

@app.get("/", response_class=HTMLResponse)
async def root():
    """根路径 - 返回HTML页面"""
    return HTMLResponse(content=HTML_CONTENT)


@app.get("/health")
async def health_check():
    """健康检查 - 检查各依赖服务状态"""
    health_status = {
        "status": "healthy",
        "version": "1.1.0",
        "service": "Deep Research Agent",
        "dependencies": {}
    }

    # 检查 Redis
    try:
        if cache_manager.is_enabled and cache_manager._redis:
            await cache_manager._redis.ping()
            health_status["dependencies"]["redis"] = "healthy"
        else:
            health_status["dependencies"]["redis"] = "disabled"
    except Exception as e:
        health_status["dependencies"]["redis"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"

    # 检查 LLM 配置
    health_status["dependencies"]["llm"] = "configured" if settings.deepseek_api_key else "missing_api_key"

    # 检查搜索工具
    health_status["dependencies"]["search"] = "available"

    return health_status


# ====== 指标端点 ======

@app.get("/metrics")
async def metrics():
    """Prometheus 指标端点"""
    return await metrics_endpoint


@app.post("/api/research")
async def create_research(request: ResearchRequest) -> Dict[str, Any]:
    """创建研究任务"""
    try:
        # 创建带进度回调的调度器
        from ..core.orchestrator import Orchestrator
        from langchain_openai import ChatOpenAI

        llm = None
        if request.enable_llm and settings.deepseek_api_key:
            llm = ChatOpenAI(
                model=settings.deepseek_model,
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                temperature=0.7
            )

        orch = Orchestrator(llm=llm, progress_callback=ws_progress_callback)
        task_id = await orch.create_research_task(request.query)

        return {
            "status": "created",
            "task_id": task_id,
            "message": "任务已创建"
        }
    except Exception as e:
        logger.error(f"创建研究任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/research/{task_id}/execute")
async def execute_research(task_id: str) -> Dict[str, Any]:
    """执行研究任务"""
    try:
        from ..core.orchestrator import Orchestrator
        from langchain_openai import ChatOpenAI

        llm = None
        if settings.deepseek_api_key:
            llm = ChatOpenAI(
                model=settings.deepseek_model,
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                temperature=0.7
            )

        orch = Orchestrator(llm=llm, progress_callback=ws_progress_callback)

        # 加载已有任务或创建新任务
        await orch.load_task(task_id)

        result = await orch.start_research(task_id, plan_approved=True)
        return result
    except Exception as e:
        logger.error(f"执行研究任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/research/{task_id}")
async def get_task_status(task_id: str) -> Dict[str, Any]:
    """获取任务状态"""
    from ..core.orchestrator import Orchestrator

    orch = Orchestrator()
    status = await orch.get_task_status(task_id)

    if not status:
        raise HTTPException(status_code=404, detail="任务不存在")

    return status


@app.post("/api/research/{task_id}/approve")
async def approve_plan(request: PlanApprovalRequest) -> Dict[str, Any]:
    """批准研究计划"""
    try:
        from ..core.orchestrator import Orchestrator

        orch = Orchestrator()
        result = await orch.approve_plan(
            request.task_id,
            request.approved,
            request.modifications
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/research")
async def list_tasks() -> List[Dict[str, Any]]:
    """列出所有任务"""
    from ..core.orchestrator import Orchestrator

    orch = Orchestrator()
    return await orch.list_tasks()


@app.get("/api/stats")
async def get_stats() -> Dict[str, Any]:
    """获取统计信息"""
    from ..core.checkpoint import checkpoint_manager
    from ..core.cache import get_cache_stats
    from ..tools.search import search_tool

    checkpoints = checkpoint_manager.list_checkpoints()
    cache_stats = await get_cache_stats()

    return {
        "total_tasks": len(checkpoints),
        "active_providers": search_tool.get_provider_info(),
        "llm_configured": bool(settings.deepseek_api_key),
        "cache": cache_stats
    }


# ====== 认证端点 ======

@app.post("/api/auth/login")
async def login(username: str, password: str):
    """用户登录"""
    # 简化实现：支持 demo 用户
    if username == "demo" and password == "demo":
        token = auth_manager.create_access_token({
            "sub": "demo",
            "username": "demo",
            "tenant_id": "tenant_demo"
        })
        return {"access_token": token, "token_type": "bearer"}
    return JSONResponse(status_code=401, content={"error": "Invalid credentials"})


@app.get("/api/auth/api-keys")
async def list_api_keys():
    """获取 API Key 列表"""
    # 返回 demo 用户的 API Key
    return {"api_keys": ["demo-api-key-12345"]}


# ==================== WebSocket端点 ====================

@app.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    """WebSocket端点 - 支持实时进度推送"""
    await manager.connect(task_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            # 处理客户端消息
            msg_type = message.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            elif msg_type == "cancel":
                # 取消任务
                from ..core.orchestrator import Orchestrator
                orch = Orchestrator()
                await orch.cancel_task(task_id)

    except WebSocketDisconnect:
        manager.disconnect(task_id, websocket)
    except Exception as e:
        logger.error(f"WebSocket错误: {e}")
        manager.disconnect(task_id, websocket)


# ==================== HTML内容 ====================

HTML_CONTENT = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Deep Research Agent | 深度研究智能体</title>
    <style>
        :root {
            --primary: #2563eb;
            --primary-dark: #1d4ed8;
            --success: #10b981;
            --warning: #f59e0b;
            --error: #ef4444;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text: #1e293b;
            --text-light: #64748b;
            --border: #e2e8f0;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }

        /* Header */
        header {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            padding: 40px 0;
            margin-bottom: 30px;
            box-shadow: 0 4px 20px rgba(37, 99, 235, 0.2);
        }

        header h1 {
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 10px;
        }

        header p {
            opacity: 0.9;
            font-size: 1.1rem;
        }

        /* Cards */
        .card {
            background: var(--card-bg);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            border: 1px solid var(--border);
        }

        .card h2 {
            font-size: 1.25rem;
            margin-bottom: 16px;
            color: var(--text);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        /* Input */
        .input-group {
            display: flex;
            gap: 12px;
            margin-bottom: 16px;
        }

        input[type="text"] {
            flex: 1;
            padding: 14px 18px;
            border: 2px solid var(--border);
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.2s;
        }

        input[type="text"]:focus {
            outline: none;
            border-color: var(--primary);
        }

        button {
            padding: 14px 28px;
            background: var(--primary);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }

        button:hover {
            background: var(--primary-dark);
            transform: translateY(-1px);
        }

        button:disabled {
            background: #94a3b8;
            cursor: not-allowed;
        }

        button.secondary {
            background: white;
            color: var(--text);
            border: 2px solid var(--border);
        }

        button.secondary:hover {
            background: #f1f5f9;
        }

        /* Progress */
        .progress-bar {
            height: 8px;
            background: var(--border);
            border-radius: 4px;
            overflow: hidden;
            margin: 16px 0;
        }

        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--primary), var(--success));
            border-radius: 4px;
            transition: width 0.3s ease;
        }

        .progress-text {
            font-size: 0.9rem;
            color: var(--text-light);
            text-align: center;
            margin-top: 8px;
        }

        /* Status */
        .status {
            padding: 12px 16px;
            border-radius: 8px;
            margin: 12px 0;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .status.waiting {
            background: #fef3c7;
            color: #92400e;
            border: 1px solid #fcd34d;
        }

        .status.success {
            background: #d1fae5;
            color: #065f46;
            border: 1px solid #6ee7b7;
        }

        .status.error {
            background: #fee2e2;
            color: #991b1b;
            border: 1px solid #fca5a5;
        }

        .status.running {
            background: #dbeafe;
            color: #1e40af;
            border: 1px solid #93c5fd;
        }

        /* Plan */
        .plan-item {
            padding: 16px;
            border-left: 4px solid var(--primary);
            margin: 12px 0;
            background: #f8fafc;
            border-radius: 0 8px 8px 0;
        }

        .plan-item h4 {
            color: var(--text);
            margin-bottom: 8px;
        }

        .plan-item .keywords {
            font-size: 0.85rem;
            color: var(--text-light);
        }

        .keyword-tag {
            display: inline-block;
            padding: 2px 8px;
            background: #e0e7ff;
            color: #4338ca;
            border-radius: 4px;
            margin: 2px 4px 2px 0;
            font-size: 0.8rem;
        }

        /* Report */
        .report-section {
            margin: 24px 0;
        }

        .report-section h3 {
            color: var(--text);
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 2px solid var(--border);
        }

        .report-section p {
            color: var(--text-light);
            line-height: 1.8;
        }

        .source-list {
            list-style: none;
        }

        .source-list li {
            padding: 8px 0;
            border-bottom: 1px solid var(--border);
        }

        .source-list a {
            color: var(--primary);
            text-decoration: none;
        }

        .source-list a:hover {
            text-decoration: underline;
        }

        /* Log */
        #log {
            background: #1e1e2e;
            color: #cdd6f4;
            padding: 20px;
            border-radius: 8px;
            font-family: 'Fira Code', monospace;
            font-size: 13px;
            max-height: 400px;
            overflow-y: auto;
        }

        .log-entry {
            margin: 6px 0;
            padding: 4px 0;
        }

        .log-time {
            color: #6c7086;
        }

        .log-progress {
            color: #89b4fa;
        }

        .log-success {
            color: #a6e3a1;
        }

        .log-error {
            color: #f38ba8;
        }

        /* Tabs */
        .tabs {
            display: flex;
            gap: 4px;
            margin-bottom: 20px;
            border-bottom: 2px solid var(--border);
        }

        .tab {
            padding: 12px 24px;
            cursor: pointer;
            border: none;
            background: none;
            font-size: 15px;
            color: var(--text-light);
            position: relative;
        }

        .tab:hover {
            color: var(--text);
        }

        .tab.active {
            color: var(--primary);
        }

        .tab.active::after {
            content: '';
            position: absolute;
            bottom: -2px;
            left: 0;
            right: 0;
            height: 2px;
            background: var(--primary);
        }

        .tab-content {
            display: none;
        }

        .tab-content.active {
            display: block;
        }

        /* Stats */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin: 20px 0;
        }

        .stat-card {
            background: #f8fafc;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
        }

        .stat-value {
            font-size: 2rem;
            font-weight: 700;
            color: var(--primary);
        }

        .stat-label {
            font-size: 0.9rem;
            color: var(--text-light);
        }

        /* Loading */
        .spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255,255,255,.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 1s ease-in-out infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        /* Responsive */
        @media (max-width: 768px) {
            .input-group {
                flex-direction: column;
            }

            header h1 {
                font-size: 1.8rem;
            }

            .stats-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <header>
        <div class="container">
            <h1>Deep Research Agent</h1>
            <p>基于LangGraph的多智能体深度研究系统</p>
        </div>
    </header>

    <div class="container">
        <div class="tabs">
            <button class="tab active" onclick="showTab('research')">开始研究</button>
            <button class="tab" onclick="showTab('tasks')">任务列表</button>
            <button class="tab" onclick="showTab('stats')">系统统计</button>
        </div>

        <!-- 研究标签页 -->
        <div id="research-tab" class="tab-content active">
            <div class="card">
                <h2>创建研究任务</h2>
                <div class="input-group">
                    <input type="text" id="query" placeholder="输入研究主题，例如：2026年人形机器人产业链的上下游机会" />
                    <button onclick="startResearch()" id="start-btn">开始研究</button>
                </div>
                <label style="display: flex; align-items: center; gap: 8px; margin-top: 12px;">
                    <input type="checkbox" id="use-llm">
                    <span>启用DeepSeek LLM智能分析（需要API Key）</span>
                </label>
            </div>

            <!-- 状态卡片 -->
            <div class="card" id="status-card" style="display: none;">
                <h2>执行状态</h2>
                <div id="status"></div>
                <div class="progress-bar">
                    <div class="progress-fill" id="progress-fill" style="width: 0%"></div>
                </div>
                <div class="progress-text" id="progress-text">等待开始...</div>
            </div>

            <!-- 计划卡片 -->
            <div class="card" id="plan-card" style="display: none;">
                <h2>研究计划</h2>
                <div id="plan"></div>
                <div class="input-group" style="margin-top: 16px;">
                    <button onclick="approvePlan(true)">批准计划</button>
                    <button class="secondary" onclick="approvePlan(false)">修改计划</button>
                </div>
            </div>

            <!-- 报告卡片 -->
            <div class="card" id="report-card" style="display: none;">
                <h2>研究报告</h2>
                <div id="report"></div>
                <div class="input-group" style="margin-top: 16px;">
                    <button onclick="exportReport('markdown')">导出Markdown</button>
                    <button class="secondary" onclick="exportReport('html')">导出HTML</button>
                </div>
            </div>

            <!-- 日志卡片 -->
            <div class="card">
                <h2>执行日志</h2>
                <div id="log">
                    <div class="log-entry"><span class="log-time">系统已就绪</span> <span class="log-success">等待用户输入...</span></div>
                </div>
            </div>
        </div>

        <!-- 任务列表标签页 -->
        <div id="tasks-tab" class="tab-content">
            <div class="card">
                <h2>历史任务</h2>
                <div id="tasks-list"></div>
            </div>
        </div>

        <!-- 统计标签页 -->
        <div id="stats-tab" class="tab-content">
            <div class="card">
                <h2>系统统计</h2>
                <div class="stats-grid" id="stats-grid"></div>
            </div>
        </div>
    </div>

    <script>
        let currentTaskId = null;
        let ws = null;

        // 标签切换
        function showTab(tab) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            event.target.classList.add('active');
            document.getElementById(tab + '-tab').classList.add('active');
            if (tab === 'tasks') loadTasks();
            if (tab === 'stats') loadStats();
        }

        // 日志
        function log(message, type = 'info') {
            const logDiv = document.getElementById('log');
            const time = new Date().toLocaleTimeString();
            const typeClass = type === 'progress' ? 'log-progress' :
                             type === 'success' ? 'log-success' :
                             type === 'error' ? 'log-error' : '';
            logDiv.innerHTML += `<div class="log-entry"><span class="log-time">[${time}]</span> <span class="${typeClass}">${message}</span></div>`;
            logDiv.scrollTop = logDiv.scrollHeight;
        }

        // 开始研究
        async function startResearch() {
            const query = document.getElementById('query').value;
            const useLlm = document.getElementById('use-llm').checked;
            if (!query) return;

            // 重置UI
            document.getElementById('status-card').style.display = 'block';
            document.getElementById('plan-card').style.display = 'none';
            document.getElementById('report-card').style.display = 'none';
            document.getElementById('progress-fill').style.width = '0%';
            document.getElementById('progress-text').textContent = '正在创建任务...';
            document.getElementById('status').innerHTML = '<div class="status running">正在初始化研究任务<span class="spinner"></span></div>';

            document.getElementById('start-btn').disabled = true;
            log('创建研究任务: ' + query);

            try {
                const response = await fetch('/api/research', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({query, enable_llm: useLlm})
                });
                const data = await response.json();
                currentTaskId = data.task_id;
                log('任务创建成功: ' + currentTaskId, 'success');

                // 连接WebSocket
                connectWebSocket(currentTaskId);

                // 开始执行
                await executeTask();
            } catch (e) {
                log('错误: ' + e, 'error');
                document.getElementById('start-btn').disabled = false;
            }
        }

        // 执行任务
        async function executeTask() {
            log('开始执行研究...', 'progress');
            document.getElementById('status').innerHTML = '<div class="status running">正在执行研究<span class="spinner"></span></div>';

            try {
                const response = await fetch('/api/research/' + currentTaskId + '/execute', {
                    method: 'POST'
                });
                const result = await response.json();
                handleResult(result);
            } catch (e) {
                log('执行错误: ' + e, 'error');
                document.getElementById('start-btn').disabled = false;
            }
        }

        // 处理结果
        function handleResult(result) {
            document.getElementById('start-btn').disabled = false;

            if (result.status === 'waiting_approval') {
                log('计划已生成，等待确认', 'progress');
                document.getElementById('status').innerHTML = '<div class="status waiting">请确认研究计划</div>';
                document.getElementById('plan-card').style.display = 'block';
                renderPlan(result.plan);
            } else if (result.status === 'success') {
                log('研究完成!', 'success');
                document.getElementById('status').innerHTML = '<div class="status success">研究完成</div>';
                document.getElementById('progress-fill').style.width = '100%';
                document.getElementById('progress-text').textContent = '完成';
                document.getElementById('report-card').style.display = 'block';
                renderReport(result.report);
            } else if (result.status === 'error') {
                log('错误: ' + result.error, 'error');
                document.getElementById('status').innerHTML = '<div class="status error">' + result.error + '</div>';
            }
        }

        // 渲染计划
        function renderPlan(plan) {
            if (!plan || !plan.tasks) return;
            let html = '';
            plan.tasks.forEach((task, i) => {
                html += '<div class="plan-item"><h4>' + (i+1) + '. ' + task.description + '</h4>';
                html += '<div class="keywords">';
                (task.search_keywords || []).forEach(kw => {
                    html += '<span class="keyword-tag">' + kw + '</span>';
                });
                html += '</div></div>';
            });
            document.getElementById('plan').innerHTML = html;
        }

        // 渲染报告
        function renderReport(report) {
            if (!report) return;
            let html = '<h3 style="font-size: 1.5rem; margin-bottom: 16px;">' + report.title + '</h3>';
            html += '<p style="font-size: 1.1rem; color: var(--text); margin-bottom: 24px;"><strong>摘要:</strong> ' + report.summary + '</p>';

            if (report.sections) {
                report.sections.forEach(section => {
                    html += '<div class="report-section"><h3>' + (section.title || '') + '</h3>';
                    html += '<p>' + (section.content || '').replace(/\\n/g, '<br>') + '</p></div>';
                });
            }

            if (report.sources && report.sources.length > 0) {
                html += '<h3>参考来源</h3><ul class="source-list">';
                report.sources.forEach(source => {
                    html += '<li><a href="' + (source.url || '#') + '" target="_blank">' + (source.title || '未命名') + '</a></li>';
                });
                html += '</ul>';
            }

            html += '<div style="margin-top: 20px; padding: 16px; background: #f0fdf4; border-radius: 8px;">';
            html += '<strong>质量评分:</strong> ' + ((report.quality_score || 0) * 100).toFixed(0) + '%';
            html += '</div>';

            document.getElementById('report').innerHTML = html;
        }

        // 批准计划
        async function approvePlan(approved) {
            if (!currentTaskId) return;
            log(approved ? '批准计划...' : '修改计划...', 'progress');

            try {
                const response = await fetch('/api/research/' + currentTaskId + '/approve', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({task_id: currentTaskId, approved})
                });
                const result = await response.json();
                handleResult(result);
            } catch (e) {
                log('批准计划错误: ' + e, 'error');
            }
        }

        // 加载任务列表
        async function loadTasks() {
            try {
                const response = await fetch('/api/research');
                const tasks = await response.json();
                if (tasks.length === 0) {
                    document.getElementById('tasks-list').innerHTML = '<p style="color: var(--text-light);">暂无历史任务</p>';
                    return;
                }
                let html = '<table style="width: 100%; border-collapse: collapse;">';
                html += '<tr style="background: #f8fafc;"><th style="padding: 12px; text-align: left;">任务ID</th><th style="padding: 12px; text-align: left;">查询</th><th style="padding: 12px; text-align: left;">状态</th><th style="padding: 12px; text-align: left;">操作</th></tr>';
                tasks.forEach(task => {
                    const status = task.report_ready ? '已完成' : '进行中';
                    html += '<tr style="border-bottom: 1px solid var(--border);">';
                    html += '<td style="padding: 12px; font-family: monospace; font-size: 0.9rem;">' + task.task_id.substring(0, 20) + '...</td>';
                    html += '<td style="padding: 12px;">' + task.query + '</td>';
                    html += '<td style="padding: 12px;"><span style="padding: 4px 8px; background: ' + (task.report_ready ? '#d1fae5' : '#dbeafe') + '; border-radius: 4px;">' + status + '</span></td>';
                    html += '<td style="padding: 12px;"><button class="secondary" style="padding: 6px 12px; font-size: 0.9rem;" onclick="viewTask(\'' + task.task_id + '\')">查看</button></td>';
                    html += '</tr>';
                });
                html += '</table>';
                document.getElementById('tasks-list').innerHTML = html;
            } catch (e) {
                log('加载任务错误: ' + e, 'error');
            }
        }

        // 查看任务
        async function viewTask(taskId) {
            currentTaskId = taskId;
            showTab('research');
            try {
                const response = await fetch('/api/research/' + taskId);
                const task = await response.json();
                document.getElementById('query').value = task.query;
                if (task.report) {
                    document.getElementById('status-card').style.display = 'block';
                    document.getElementById('report-card').style.display = 'block';
                    document.getElementById('status').innerHTML = '<div class="status success">任务已完成</div>';
                    renderReport(task.report);
                }
            } catch (e) {
                log('加载任务错误: ' + e, 'error');
            }
        }

        // 加载统计
        async function loadStats() {
            try {
                const response = await fetch('/api/stats');
                const stats = await response.json();
                document.getElementById('stats-grid').innerHTML = `
                    <div class="stat-card">
                        <div class="stat-value">${stats.total_tasks}</div>
                        <div class="stat-label">总任务数</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${stats.active_providers?.available?.length || 0}</div>
                        <div class="stat-label">搜索提供者</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" style="color: ${stats.llm_configured ? '#10b981' : '#f59e0b'}">${stats.llm_configured ? '已配置' : '未配置'}</div>
                        <div class="stat-label">DeepSeek LLM</div>
                    </div>
                `;
            } catch (e) {
                log('加载统计错误: ' + e, 'error');
            }
        }

        // WebSocket连接
        function connectWebSocket(taskId) {
            if (ws) ws.close();
            ws = new WebSocket('ws://localhost:8000/ws/' + taskId);

            ws.onopen = () => log('WebSocket连接已建立', 'success');

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                log('收到: ' + data.type, 'progress');

                if (data.type === 'progress') {
                    document.getElementById('progress-fill').style.width = data.progress + '%';
                    document.getElementById('progress-text').textContent = data.message;
                } else if (data.type === 'plan_ready') {
                    document.getElementById('plan-card').style.display = 'block';
                    renderPlan(data.plan);
                } else if (data.type === 'report_ready') {
                    document.getElementById('report-card').style.display = 'block';
                    renderReport(data.report);
                }
            };

            ws.onerror = (err) => log('WebSocket错误', 'error');
            ws.onclose = () => log('WebSocket连接关闭', 'info');
        }

        // 导出报告
        function exportReport(format) {
            log('导出' + format + '格式...', 'progress');
            // TODO: 实现导出功能
            alert('导出功能开发中...');
        }

        // 页面加载
        loadStats();
    </script>
</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)