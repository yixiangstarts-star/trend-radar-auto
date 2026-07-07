"""日报生成器：将处理后的新闻数据生成Markdown格式日报"""

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict

logger = logging.getLogger(__name__)

CST = timezone(timedelta(hours=8))


class ReportGenerator:
    """日报 Markdown 生成器"""

    def __init__(self, categories: Dict[str, str] = None):
        """
        Args:
            categories: 分类名称映射 {"C01": "AI与大模型", ...}
        """
        self.categories = categories or {}

    def generate_daily_report(self, articles: List[Dict]) -> str:
        """生成完整日报"""
        now = datetime.now(CST)
        date_str = now.strftime("%Y年%m月%d日")

        sections = []

        # 页头
        sections.append(self._header(date_str, len(articles)))

        # Top 10 热点
        top_articles = articles[:10]
        if top_articles:
            sections.append(self._top10_section(top_articles))

        # 热度分布
        sections.append(self._heat_distribution(articles))

        # 分类汇总
        sections.append(self._category_summary(articles))

        # 完整列表（Top 10之外）
        if len(articles) > 10:
            sections.append(self._full_list_section(articles[10:]))

        # 页脚
        sections.append(self._footer())

        return "\n\n".join(sections)

    def _header(self, date_str: str, total: int) -> str:
        """日报页头"""
        return f"""## 📅 {date_str} 科技新闻采集报告

> 🤖 自动采集时间：{datetime.now(CST).strftime('%H:%M')} | 采集源：5个（MVP阶段） | 入库新闻：{total}篇

---

## 🔥 数据概览

| 指标 | 数值 |
|------|------|
| 采集源 | 36氪、虎嗅、机器之心、IT之家、Solidot |
| 去重后新闻数 | {total} 篇 |
| 生成时间 | {datetime.now(CST).strftime('%Y-%m-%d %H:%M')} |"""

    def _top10_section(self, articles: List[Dict]) -> str:
        """Top 10 热点"""
        lines = ["## 📈 今日 Top 10 热点\n"]

        for i, a in enumerate(articles, 1):
            level = a.get("heat_emoji", "·")
            score = a.get("heat_score", 0)
            title = a.get("title", "无标题")
            link = a.get("link", "")
            source = a.get("source", "")
            cats = ", ".join(a.get("category_names", []))

            lines.append(
                f"### {i}. {level} [{score:.0f}分] {title}\n\n"
                f"📡 来源：{source} | 📂 分类：{cats}\n\n"
                + (f"🔗 [阅读原文]({link})\n" if link else "")
                + (f"\n{a.get('deep_summary', '')}\n" if a.get("deep_summary") else "")
                + "\n---\n"
            )

        return "\n".join(lines)

    def _heat_distribution(self, articles: List[Dict]) -> str:
        """热度分布统计"""
        stats = {"S": 0, "A": 0, "B": 0, "C": 0}
        for a in articles:
            lv = a.get("heat_level", "C")
            stats[lv] = stats.get(lv, 0) + 1

        return f"""## 📊 热度分布

| 等级 | 数量 | 说明 |
|------|------|------|
| 🔥🔥🔥 S级 | {stats['S']} 篇 | 高度关注，建议优先做视频 |
| 🔥🔥 A级 | {stats['A']} 篇 | 重要新闻，可跟进 |
| 🔥 B级 | {stats['B']} 篇 | 行业动态，了解即可 |
| · C级 | {stats['C']} 篇 | 一般资讯 |"""

    def _category_summary(self, articles: List[Dict]) -> str:
        """分类汇总"""
        cat_count = {}
        for a in articles:
            cats = a.get("categories", ["C04"])
            for c in cats:
                cat_count[c] = cat_count.get(c, 0) + 1

        lines = ["## 📂 分类覆盖\n"]
        lines.append("| 分类 | 数量 |")
        lines.append("|------|------|")
        for code, name in sorted(self.categories.items()):
            count = cat_count.get(code, 0)
            bar = "█" * min(count, 20)
            lines.append(f"| {name} | {count} {bar} |")

        return "\n".join(lines)

    def _full_list_section(self, articles: List[Dict]) -> str:
        """完整新闻列表（简化版）"""
        lines = ["## 📋 其余新闻列表\n"]
        for i, a in enumerate(articles, 1):
            title = a.get("title", "无标题")
            link = a.get("link", "")
            source = a.get("source", "")
            level = a.get("heat_emoji", "·")

            lines.append(
                f"{i}. {level} **{title}** — {source}"
                + (f" [🔗]({link})" if link else "")
            )

        return "\n".join(lines)

    def _footer(self) -> str:
        """日报页脚"""
        return f"""---

> 📌 本日报由「科技新闻每日采集系统」自动生成
> ⏰ 下次采集：明天 09:00（北京时间）
> 🔧 MVP阶段：5个RSS源 | 后续将扩展至46个采集源
"""

    def generate_category_markdown(
        self, category_code: str, articles: List[Dict], date_str: str = ""
    ) -> str:
        """为单个分类生成追加用的Markdown"""
        if not articles:
            return ""

        cat_name = self.categories.get(category_code, category_code)

        lines = [f"### {date_str} {cat_name} 更新\n"]
        for a in articles:
            title = a.get("title", "无标题")
            link = a.get("link", "")
            summary = a.get("summary", "")[:150]

            lines.append(
                f"- **{title}**\n"
                + (f"  🔗 {link}\n" if link else "")
                + (f"  📝 {summary}...\n" if summary else "")
            )

        return "\n".join(lines)
