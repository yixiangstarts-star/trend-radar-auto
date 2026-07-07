"""RSS 采集器：从配置的RSS源拉取新闻"""

import ssl
import feedparser
import hashlib
import logging
import requests
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from urllib3.exceptions import InsecureRequestWarning

# 抑制 SSL 警告（部分源证书链不完整）
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

logger = logging.getLogger(__name__)

# 北京时间时区
CST = timezone(timedelta(hours=8))


class RSSCollector:
    """RSS 新闻采集器"""

    def __init__(self, sources: List[Dict], lookback_hours: int = 24):
        """
        Args:
            sources: RSS源配置列表 [{"name": "36氪", "url": "...", ...}, ...]
            lookback_hours: 采集过去多少小时的新闻
        """
        self.sources = sources
        self.lookback_hours = lookback_hours

    def collect_all(self) -> List[Dict]:
        """采集所有RSS源的新闻

        Returns:
            新闻列表，每条包含：
            {
                "id": str,           # 标题+来源生成的唯一ID
                "title": str,        # 标题
                "link": str,         # 原文链接
                "summary": str,      # 摘要
                "published": datetime, # 发布时间
                "source": str,       # 来源名称
                "source_url": str,   # RSS源URL
                "category_hint": list, # 分类提示
                "authority_score": int, # 媒体权威分
                "_raw": dict         # 原始feed条目
            }
        """
        all_articles = []
        for source in self.sources:
            try:
                articles = self._collect_one(source)
                all_articles.extend(articles)
                logger.info(f"[{source['name']}] 采集到 {len(articles)} 篇")
            except Exception as e:
                logger.error(f"[{source['name']}] 采集失败: {e}")

        logger.info(f"总计采集 {len(all_articles)} 篇新闻（来自 {len(self.sources)} 个源）")
        return all_articles

    def _fallback_parse(self, raw_content: bytes) -> list:
        """正则暴力解析：当 feedparser 因 XML 格式错误完全失败时的兜底方案

        从原始 XML 字节流中用正则提取 <item> / <entry> 中的标题、链接、摘要。
        返回 feedparser 兼容的 entry 字典列表。
        """
        import re

        text = raw_content.decode("utf-8", errors="replace")

        # 匹配 <item>...</item> (RSS 2.0) 或 <entry>...</entry> (Atom)
        entries_raw = re.findall(
            r"<(?:item|entry)\b[^>]*>(.*?)</(?:item|entry)>",
            text,
            re.DOTALL | re.IGNORECASE,
        )

        entries = []
        for block in entries_raw:
            title_m = re.search(r"<title[^>]*>(.*?)</title>", block, re.DOTALL | re.IGNORECASE)
            link_m = re.search(r"<link[^>]*href=[\"']([^\"']+)[\"']", block, re.IGNORECASE)
            if not link_m:
                link_m = re.search(r"<link[^>]*>(.*?)</link>", block, re.DOTALL | re.IGNORECASE)
            desc_m = re.search(
                r"<(?:description|summary|content)[^>]*>(.*?)</(?:description|summary|content)>",
                block,
                re.DOTALL | re.IGNORECASE,
            )

            title = re.sub(r"<[^>]+>", "", (title_m.group(1) if title_m else "")).strip()
            link = (link_m.group(1) if link_m else "").strip()
            desc = re.sub(r"<[^>]+>", "", (desc_m.group(1) if desc_m else "")).strip()

            if title and link:
                entries.append({
                    "title": title,
                    "link": link,
                    "summary": desc or title,
                })

        logger.info(f"[fallback] 正则提取到 {len(entries)} 条")
        return entries

    def _collect_one(self, source: Dict) -> List[Dict]:
        """采集单个RSS源（支持SSL容错 + 宽松XML解析）"""
        articles = []
        url = source["url"]

        # 先通过 requests 获取内容（支持 SSL 容错），再喂给 feedparser
        # 这样可以同时解决 SSL 证书问题和部分奇怪的编码问题
        try:
            resp = requests.get(
                url,
                timeout=30,
                verify=False,  # 容忍自签名/不完整证书链
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                    "Accept": "application/rss+xml, application/xml, text/xml, */*",
                },
            )
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
        except requests.RequestException as e:
            # 网络层面的失败，回退到 feedparser 直连
            logger.warning(f"[{source['name']}] requests 获取失败 ({e})，尝试 feedparser 直连")
            resp = None
            feed = feedparser.parse(url)

        # bozo 仅代表 XML 不规范，不代表没有内容
        if feed.bozo:
            bozo_msg = str(feed.bozo_exception) if feed.bozo_exception else "unknown"
            if feed.entries:
                logger.info(
                    f"[{source['name']}] XML 不规范（{bozo_msg[:80]}），"
                    f"但解析到 {len(feed.entries)} 条"
                )
            else:
                # feedparser 完全失败，用正则 fallback 暴力提取
                logger.warning(
                    f"[{source['name']}] feedparser 解析失败 ({bozo_msg[:100]})，"
                    f"尝试正则 fallback"
                )
                # 确保有原始内容（resp 在直连 fallback 时可能为 None）
                raw = resp.content if resp else None
                if raw is None:
                    try:
                        r = requests.get(url, timeout=30, verify=False)
                        raw = r.content
                    except Exception:
                        pass
                if raw:
                    fallback_entries = self._fallback_parse(raw)
                    if fallback_entries:
                        feed.entries = fallback_entries
                    else:
                        logger.warning(f"[{source['name']}] 正则 fallback 也失败，跳过此源")
                        return articles
                else:
                    logger.warning(f"[{source['name']}] 无法获取原始内容，跳过此源")
                    return articles

        cutoff_time = datetime.now(CST) - timedelta(hours=self.lookback_hours)

        for entry in feed.entries:
            # 解析发布时间
            published = self._parse_published(entry)

            # 过滤：只保留 lookback_hours 内的新闻
            if published and published < cutoff_time:
                continue

            # 生成唯一ID
            article_id = self._generate_id(entry.get("title", ""), source["name"])

            # 提取摘要
            summary = self._extract_summary(entry)

            articles.append({
                "id": article_id,
                "title": entry.get("title", "").strip(),
                "link": entry.get("link", ""),
                "summary": summary,
                "published": published or datetime.now(CST),
                "source": source["name"],
                "source_url": source["url"],
                "category_hint": source.get("category_hint", []),
                "authority_score": source.get("authority_score", 5),
                "_raw": entry
            })

        return articles

    def _parse_published(self, entry) -> Optional[datetime]:
        """解析RSS条目的发布时间"""
        # 尝试多个时间字段
        for field in ["published_parsed", "updated_parsed", "created_parsed"]:
            time_tuple = getattr(entry, field, None)
            if time_tuple:
                try:
                    dt = datetime(*time_tuple[:6])
                    # 如果有时区信息就保留，否则假设为北京时间
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=CST)
                    return dt
                except (ValueError, TypeError):
                    continue
        return None

    def _extract_summary(self, entry) -> str:
        """提取新闻摘要，去除HTML标签"""
        import re

        summary = ""
        for field in ["summary", "description", "content"]:
            raw = getattr(entry, field, "")
            if raw:
                # 取第一个匹配的
                if isinstance(raw, list) and len(raw) > 0:
                    summary = raw[0].get("value", "")
                elif isinstance(raw, str):
                    summary = raw
                if summary:
                    break

        # 去除HTML标签
        summary = re.sub(r"<[^>]+>", "", summary)
        # 去除多余空白
        summary = re.sub(r"\s+", " ", summary).strip()
        # 截断到300字
        if len(summary) > 300:
            summary = summary[:300] + "..."

        return summary

    def _generate_id(self, title: str, source: str) -> str:
        """生成文章唯一ID"""
        raw = f"{title.strip()}|{source}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]
