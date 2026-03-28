"""CLI界面"""
import asyncio
import sys
import json
import logging
from typing import Optional

from ..core.orchestrator import orchestrator, InterventionPoint
from ..core.schema import ResearchPlan, ResearchReport

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CLI:
    """命令行界面"""

    def __init__(self):
        self.orchestrator = orchestrator

        # 注册回调
        self.orchestrator.register_callback(
            InterventionPoint.PLAN_APPROVAL,
            self._on_plan_approval
        )
        self.orchestrator.register_callback(
            InterventionPoint.REPORT_REVIEW,
            self._on_report_review
        )

        self.current_task_id: Optional[str] = None

    async def _on_plan_approval(self, data: dict) -> dict:
        """计划确认回调"""
        plan = data.get("plan")
        if plan:
            print("\n" + "="*50)
            print("研究计划已生成:")
            print("="*50)

            tasks = plan.get("tasks", [])
            for i, task in enumerate(tasks, 1):
                print(f"\n{i}. {task.get('description')}")
                print(f"   关键词: {', '.join(task.get('search_keywords', []))}")

            print("\n" + "="*50)
        return {}

    async def _on_report_review(self, data: dict) -> dict:
        """报告审阅回调"""
        report = data.get("report")
        if report:
            print("\n" + "="*50)
            print("研究报告已生成!")
            print("="*50)
        return {}

    async def start(self):
        """启动CLI"""
        print("="*50)
        print("深度研究智能体 (Deep Research Agent)")
        print("="*50)
        print("\n输入研究主题开始研究，或输入 'help' 查看帮助。")
        print("输入 'exit' 退出。\n")

        while True:
            try:
                query = input("研究主题> ").strip()

                if query.lower() in ["exit", "quit", "q"]:
                    print("再见!")
                    break

                if query.lower() == "help":
                    self._print_help()
                    continue

                if not query:
                    continue

                # 创建任务
                task_id = await self.orchestrator.create_research_task(query)
                self.current_task_id = task_id
                print(f"\n任务已创建: {task_id}")

                # 首次运行需要用户确认计划
                result = await self.orchestrator.start_research(task_id)

                # 处理结果
                await self._handle_result(result)

            except KeyboardInterrupt:
                print("\n\n退出中...")
                break
            except Exception as e:
                print(f"错误: {e}")

    async def _handle_result(self, result: dict):
        """处理执行结果"""
        status = result.get("status")

        if status == "waiting_approval":
            print("\n需要确认研究计划:")
            print(json.dumps(result.get("plan"), ensure_ascii=False, indent=2))

            approval = input("\n是否批准该计划? (y/n): ").strip().lower()

            if approval == "y":
                # 批准计划并继续
                result = await self.orchestrator.approve_plan(
                    self.current_task_id, approved=True
                )
                await self._handle_result(result)
            else:
                print("请修改计划或重新输入研究主题。")

        elif status == "success":
            report = result.get("report")
            if report:
                self._print_report(report)

        elif status == "error":
            print(f"\n错误: {result.get('error')}")

        elif status == "partial":
            print("\n部分完成:")
            if result.get("report"):
                self._print_report(result.get("report"))
            if result.get("error"):
                print(f"错误: {result.get('error')}")

    def _print_report(self, report: dict):
        """打印报告"""
        print("\n" + "="*50)
        print(f"研究报告: {report.get('title', '未命名')}")
        print("="*50)

        # 执行摘要
        print(f"\n{report.get('summary', '')}\n")

        # 章节
        sections = report.get("sections", [])
        for section in sections:
            print(f"--- {section.get('title', '')} ---")
            content = section.get("content", "")
            # 限制输出长度
            if len(content) > 500:
                content = content[:500] + "..."
            print(content)
            print()

        # 来源
        sources = report.get("sources", [])
        if sources:
            print("--- 参考来源 ---")
            for source in sources[:10]:
                print(f"- {source.get('title', '')}")
                print(f"  {source.get('url', '')}")
            print()

        # 导出选项
        export = input("是否导出报告? (m)arkdown/(h)tml/(n): ").strip().lower()
        if export == "m":
            filename = f"report_{self.current_task_id}.md"
            self._export_report(report, "markdown", filename)
        elif export == "h":
            filename = f"report_{self.current_task_id}.html"
            self._export_report(report, "html", filename)

    def _export_report(self, report: dict, format: str, filename: str):
        """导出报告"""
        from ..agents.writer import WriterAgent
        writer = WriterAgent()

        if format == "markdown":
            content = writer._export_markdown(ResearchReport(**report))
        else:
            content = writer._export_html(ResearchReport(**report))

        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"报告已导出到: {filename}")

    def _print_help(self):
        """打印帮助"""
        help_text = """
可用命令:
  help     - 显示帮助
  exit     - 退出程序

使用说明:
  1. 输入研究主题开始研究
  2. 系统会生成研究计划并等待确认
  3. 确认后系统执行搜索、评估、写作
  4. 生成报告后可导出为Markdown或HTML
"""
        print(help_text)


async def run_cli():
    """运行CLI"""
    cli = CLI()
    await cli.start()


if __name__ == "__main__":
    asyncio.run(run_cli())