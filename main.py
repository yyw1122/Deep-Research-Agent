"""主入口文件"""
import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from deep_research_agent.ui.cli import run_cli
from deep_research_agent.ui.web import app
from deep_research_agent.config.settings import settings
import uvicorn


def create_llm():
    """创建DeepSeek LLM"""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.deepseek_model,
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        temperature=0.7,
        max_tokens=4000
    )


async def progress_handler(progress_data):
    """进度回调处理"""
    phase = progress_data.get("phase", "")
    progress = progress_data.get("progress", 0)
    message = progress_data.get("message", "")
    print(f"\r[{progress:3d}%] {message}", end="", flush=True)


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="深度研究智能体")
    parser.add_argument("mode", nargs="?", choices=["cli", "web", "api"],
                       default="cli", help="运行模式: cli, web, api")
    parser.add_argument("--host", default=settings.host, help="服务器地址")
    parser.add_argument("--port", type=int, default=settings.port, help="服务器端口")
    parser.add_argument("--query", help="直接指定研究查询")

    args = parser.parse_args()

    if args.mode == "cli":
        # CLI模式
        if args.query:
            from deep_research_agent.core.orchestrator import Orchestrator

            async def run_single_query():
                llm = create_llm()
                orch = Orchestrator(llm=llm, progress_callback=progress_handler)
                task_id = await orch.create_research_task(args.query)
                result = await orch.start_research(task_id, plan_approved=True)
                print()  # 换行
                return result

            result = asyncio.run(run_single_query())
            if result.get("report"):
                report = result["report"]
                print(f"\n{'='*60}")
                print(f"研究报告: {report.get('title', '未命名')}")
                print(f"{'='*60}")
                print(f"\n{report.get('summary', '')}")
                print(f"\n质量评分: {report.get('quality_score', 0)}")
        else:
            asyncio.run(run_cli())

    elif args.mode in ["web", "api"]:
        # Web/API模式
        print(f"启动Web服务器: http://{args.host}:{args.port}")
        uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()