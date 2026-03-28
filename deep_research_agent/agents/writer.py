"""写作智能体"""
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime

from .base import BaseAgent
from ..core.schema import ResearchReport, Source, TaskStatus
from ..core.state import AgentType

logger = logging.getLogger(__name__)


class WriterAgent(BaseAgent):
    """写作智能体 - 负责研究报告生成"""

    def __init__(self, llm=None):
        super().__init__(
            name="WriterAgent",
            description="负责整合信息并生成结构化研究报告"
        )
        self.llm = llm
        self._report_template = {
            "executive_summary": "",
            "introduction": "",
            "main_findings": [],
            "analysis": [],
            "conclusions": [],
            "recommendations": [],
            "appendices": []
        }

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行报告生成任务"""
        query = input_data.get("query", "")
        search_results = input_data.get("search_results", {})
        evaluations = input_data.get("evaluations", {})

        if not search_results:
            return self.create_response(
                status="error",
                error="没有搜索结果可用于生成报告"
            )

        try:
            # 生成报告
            report = await self._generate_report(
                query, search_results, evaluations
            )

            return self.create_response(
                status="success",
                data={
                    "report": report.model_dump(),
                    "sections_count": len(report.sections),
                    "sources_count": len(report.sources),
                    "quality_score": report.quality_score
                }
            )

        except Exception as e:
            logger.error(f"报告生成失败: {e}")
            return self.create_response(
                status="error",
                error=str(e)
            )

    def execute_sync(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """同步执行报告生成任务"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(self.execute(input_data))

    async def _generate_report(self, query: str,
                               search_results: Dict[str, List[Dict]],
                               evaluations: Dict[str, Any]) -> ResearchReport:
        """生成研究报告"""
        if self.llm:
            return await self._llm_generate_report(query, search_results, evaluations)

        return self._rule_based_report(query, search_results, evaluations)

    async def _llm_generate_report(self, query: str,
                                   search_results: Dict[str, List[Dict]],
                                   evaluations: Dict[str, Any]) -> ResearchReport:
        """使用LLM生成报告"""
        # 准备搜索结果数据
        all_results = []
        for task_id, results in search_results.items():
            for result in results:
                all_results.append({
                    "task_id": task_id,
                    **result
                })

        # 按评估分数筛选高质量结果
        if evaluations:
            # 简化：取评估分数最高的前N个结果
            sorted_results = sorted(
                all_results,
                key=lambda x: x.get("relevance_score", 0),
                reverse=True
            )
            top_results = sorted_results[:20]
        else:
            top_results = all_results[:20]

        # 构建prompt
        prompt = f"""请根据以下研究任务和收集的信息生成一份专业的研究报告。

研究任务: {query}

收集的信息:
{self._format_results(top_results)}

请生成结构化报告，包含以下部分:
1. 执行摘要 (executive_summary): 简洁总结研究发现
2. 引言 (introduction): 介绍研究背景和目标
3. 主要发现 (main_findings): 列出关键发现
4. 分析 (analysis): 深入分析
5. 结论 (conclusions): 总结研究结论
6. 建议 (recommendations): 提出建议
7. 参考来源 (sources): 列出主要信息来源

请以JSON格式返回:
{{
    "title": "报告标题",
    "summary": "执行摘要",
    "sections": [
        {{"title": "章节标题", "content": "章节内容"}}
    ],
    "sources": [
        {{"url": "来源URL", "title": "来源标题"}}
    ]
}}
"""
        try:
            response = await self.llm.ainvoke(prompt)

            # 调试
            logger.debug(f"LLM响应: {response}")

            # 处理不同的响应格式
            response_content = ""
            if hasattr(response, 'content'):
                response_content = response.content
            elif hasattr(response, 'text'):
                response_content = response.text
            elif isinstance(response, str):
                response_content = response
            else:
                response_content = str(response)

            report_data = self._parse_llm_response(response_content)

            # 创建Sources
            sources = []
            for src in report_data.get("sources", []):
                sources.append(Source(
                    url=src.get("url", ""),
                    title=src.get("title", ""),
                    content="",
                    source_type="web"
                ))

            # 构建sections
            sections = []
            for section in report_data.get("sections", []):
                sections.append({
                    "title": section.get("title", ""),
                    "content": section.get("content", "")
                })

            # 添加执行摘要
            sections.insert(0, {
                "title": "执行摘要",
                "content": report_data.get("summary", "")
            })

            report = ResearchReport(
                title=report_data.get("title", query),
                summary=report_data.get("summary", ""),
                sections=sections,
                sources=sources,
                quality_score=0.85
            )

            return report

        except Exception as e:
            logger.warning(f"LLM报告生成失败，回退到规则: {e}")
            return self._rule_based_report(query, search_results, evaluations)

    def _rule_based_report(self, query: str,
                          search_results: Dict[str, List[Dict]],
                          evaluations: Dict[str, Any]) -> ResearchReport:
        """基于规则的报告生成"""
        # 收集所有搜索结果
        all_results = []
        for task_id, results in search_results.items():
            all_results.extend(results)

        # 构建章节
        sections = []

        # 执行摘要
        sections.append({
            "title": "执行摘要",
            "content": f"本报告针对\"{query}\"进行了深入研究，"
                      f"共收集了{len(all_results)}个相关信息源。"
        })

        # 引言
        sections.append({
            "title": "引言",
            "content": f"本研究报告旨在分析\"{query}\"的相关信息，"
                      f"为用户提供全面的行业洞察和决策参考。"
        })

        # 主要发现
        findings_content = []
        for i, result in enumerate(all_results[:10], 1):
            title = result.get("title", "未知")
            snippet = result.get("snippet", "")
            findings_content.append(f"{i}. {title}: {snippet[:100]}...")

        sections.append({
            "title": "主要发现",
            "content": "\n".join(findings_content)
        })

        # 分析
        sections.append({
            "title": "分析",
            "content": "基于收集的信息，我们进行了综合分析，"
                      "包括市场趋势、竞争格局、技术发展等方面。"
        })

        # 结论
        sections.append({
            "title": "结论",
            "content": f"通过对\"{query}\"相关信息的综合分析，"
                      f"我们得出以下主要结论..."
        })

        # 建议
        sections.append({
            "title": "建议",
            "content": "基于研究结果，我们提出以下建议..."
        })

        # 构建来源
        sources = []
        for result in all_results[:15]:
            sources.append(Source(
                url=result.get("url", ""),
                title=result.get("title", ""),
                snippet=result.get("snippet", ""),
                source_type="web"
            ))

        return ResearchReport(
            title=f"关于{query}的研究报告",
            summary=f"本报告对\"{query}\"进行了全面研究，共收集{len(all_results)}个信息源。",
            sections=sections,
            sources=sources,
            quality_score=0.6
        )

    def _format_results(self, results: List[Dict[str, Any]]) -> str:
        """格式化搜索结果"""
        formatted = []
        for i, result in enumerate(results, 1):
            formatted.append(
                f"{i}. 标题: {result.get('title', '未知')}\n"
                f"   摘要: {result.get('snippet', '')[:200]}\n"
                f"   来源: {result.get('url', '')}\n"
            )
        return "\n".join(formatted)

    def _parse_llm_response(self, content: str) -> Dict[str, Any]:
        """解析LLM响应"""
        import json
        import re

        # 尝试提取JSON
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # 备用：简单解析
        return {
            "title": "研究报告",
            "summary": content[:500],
            "sections": [],
            "sources": []
        }

    async def modify_report(self, report: ResearchReport,
                          modifications: Dict[str, Any]) -> ResearchReport:
        """修改报告"""
        if "add_section" in modifications:
            for section in modifications["add_section"]:
                report.sections.append(section)

        if "modify_section" in modifications:
            for mod in modifications["modify_section"]:
                section_title = mod.get("title")
                for section in report.sections:
                    if section.get("title") == section_title:
                        section["content"] = mod.get("content", section.get("content"))
                        break

        if "add_source" in modifications:
            for source in modifications["add_source"]:
                report.sources.append(Source(**source))

        return report

    async def export_report(self, report: ResearchReport,
                           format: str = "markdown") -> str:
        """导出报告"""
        if format == "markdown":
            return self._export_markdown(report)
        elif format == "html":
            return self._export_html(report)
        elif format == "json":
            return report.model_dump_json(indent=2)
        else:
            raise ValueError(f"不支持的格式: {format}")

    def _export_markdown(self, report: ResearchReport) -> str:
        """导出为Markdown"""
        md = f"# {report.title}\n\n"
        md += f"**生成时间**: {report.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        md += f"## 执行摘要\n\n{report.summary}\n\n"

        for section in report.sections:
            md += f"## {section.get('title', '')}\n\n"
            md += f"{section.get('content', '')}\n\n"

        md += "## 参考来源\n\n"
        for source in report.sources:
            md += f"- [{source.title}]({source.url})\n"

        return md

    def _export_html(self, report: ResearchReport) -> str:
        """导出为HTML"""
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{report.title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #333; }}
        h2 {{ color: #666; }}
        .source {{ font-size: 0.9em; color: #888; }}
    </style>
</head>
<body>
    <h1>{report.title}</h1>
    <p><em>生成时间: {report.created_at.strftime('%Y-%m-%d %H:%M:%S')}</em></p>

    <h2>执行摘要</h2>
    <p>{report.summary}</p>
"""
        for section in report.sections:
            html += f"""
    <h2>{section.get('title', '')}</h2>
    <p>{section.get('content', '')}</p>
"""

        html += """
    <h2>参考来源</h2>
    <ul>
"""
        for source in report.sources:
            html += f'        <li><a href="{source.url}">{source.title}</a></li>\n'

        html += """
    </ul>
</body>
</html>"""

        return html