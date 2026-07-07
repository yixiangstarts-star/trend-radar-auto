"""摘要生成模块：为Top N新闻生成摘要"""

import logging
import os
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class Summarizer:
    """新闻摘要生成器

    策略：
    - MVP阶段：提取RSS原文摘要（前200字）+ 标关键信息
    - AI增强阶段：调用大模型API生成高质量摘要
    """

    def __init__(self, use_ai: bool = False, api_key: str = None, api_base: str = None):
        """
        Args:
            use_ai: 是否使用AI生成摘要
            api_key: AI API密钥
            api_base: AI API地址
        """
        self.use_ai = use_ai
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.api_base = api_base or os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")

    def generate(self, articles: List[Dict], top_n: int = 10) -> List[Dict]:
        """为Top N新闻生成摘要"""
        for i, article in enumerate(articles):
            if i < top_n:
                article["deep_summary"] = self._generate_one(article, detailed=True)
            else:
                article["deep_summary"] = self._generate_one(article, detailed=False)

        return articles

    def _generate_one(self, article: Dict, detailed: bool = False) -> str:
        """为单篇新闻生成摘要"""
        title = article.get("title", "无标题")
        summary = article.get("summary", "")
        source = article.get("source", "")

        if detailed:
            if self.use_ai and self.api_key:
                return self._ai_summary(title, summary, source)
            else:
                return self._rule_summary(article)
        else:
            # 简短版：标题 + 一句话摘要
            short = summary[:100] if summary else ""
            return f"**{title}**" + (f" — {short}..." if short else "")

    def _rule_summary(self, article: Dict) -> str:
        """基于规则的摘要生成"""
        title = article.get("title", "无标题")
        summary = article.get("summary", "")
        source = article.get("source", "")
        link = article.get("link", "")

        parts = [
            f"📰 **{title}**",
            f"📡 来源：{source}",
        ]

        if summary:
            # 取前200字作为核心摘要
            core = summary[:200]
            if len(summary) > 200:
                core += "..."
            parts.append(f"📝 {core}")

        if link:
            parts.append(f"🔗 [阅读原文]({link})")

        return "\n\n".join(parts)

    def _ai_summary(self, title: str, summary: str, source: str) -> str:
        """使用AI生成摘要"""
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key, base_url=self.api_base)

            prompt = f"""请为以下科技新闻生成一段150字以内的精炼摘要（中文）：

标题：{title}
原文摘要：{summary}
来源：{source}

要求：
1. 一句话概括核心事件
2. 说明为什么值得关注（对科技创作者的价值）
3. 用中文输出"""

            response = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.3,
            )

            ai_summary = response.choices[0].message.content.strip()
            return f"📰 **{title}**\n\n🤖 AI摘要：{ai_summary}\n\n📡 来源：{source}"

        except ImportError:
            logger.warning("openai 库未安装，回退到规则摘要")
            return self._rule_summary({"title": title, "summary": summary, "source": source, "link": ""})
        except Exception as e:
            logger.error(f"AI摘要生成失败: {e}，回退到规则摘要")
            return self._rule_summary({"title": title, "summary": summary, "source": source, "link": ""})
