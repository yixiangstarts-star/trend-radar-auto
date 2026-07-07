"""去重模块：基于标题相似度的新闻去重"""

import logging
import re
from typing import List, Dict

logger = logging.getLogger(__name__)


class Deduplicator:
    """新闻去重器"""

    def __init__(self, threshold: float = 0.8):
        """
        Args:
            threshold: 相似度阈值（0-1），超过此值视为重复
        """
        self.threshold = threshold

    def deduplicate(self, articles: List[Dict]) -> List[Dict]:
        """对新闻列表去重

        策略：
        1. URL完全相同 → 直接去重
        2. 标题相似度 > threshold → 保留发布时间最早的，合并来源
        """
        if not articles:
            return []

        # 第一步：URL完全相同去重
        seen_urls = set()
        url_deduped = []
        for article in articles:
            link = article.get("link", "")
            if link and link in seen_urls:
                continue
            seen_urls.add(link)
            url_deduped.append(article)

        logger.info(f"URL去重: {len(articles)} → {len(url_deduped)}")

        # 第二步：标题相似度去重
        if len(url_deduped) <= 1:
            return url_deduped

        result = []
        merged_indices = set()

        for i, a1 in enumerate(url_deduped):
            if i in merged_indices:
                continue

            # 收集所有与 a1 相似的条目
            group = [a1]
            for j, a2 in enumerate(url_deduped):
                if j <= i or j in merged_indices:
                    continue
                sim = self._title_similarity(a1["title"], a2["title"])
                if sim >= self.threshold:
                    group.append(a2)
                    merged_indices.add(j)

            # 合并组：保留最早的发布时间，合并来源
            merged = self._merge_group(group)
            result.append(merged)
            merged_indices.add(i)

        logger.info(f"标题去重: {len(url_deduped)} → {len(result)}")
        return result

    def _title_similarity(self, title1: str, title2: str) -> float:
        """计算两个标题的相似度（基于Jaccard系数）"""
        t1 = self._tokenize(title1)
        t2 = self._tokenize(title2)

        if not t1 or not t2:
            return 0.0

        set1 = set(t1)
        set2 = set(t2)

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0

    def _tokenize(self, text: str) -> List[str]:
        """中文分词"""
        import jieba

        # 去除标点和特殊字符
        text = re.sub(r"[^\w\u4e00-\u9fff]", " ", text)
        # jieba分词，取长度>=2的词
        words = [w for w in jieba.cut(text) if len(w) >= 2]
        return words

    def _merge_group(self, group: List[Dict]) -> Dict:
        """合并一组相似新闻"""
        # 按发布时间排序，保留最早的
        group.sort(key=lambda x: x.get("published"))
        primary = group[0].copy()

        # 合并所有来源和分类提示
        all_sources = list(set(a["source"] for a in group))
        all_categories = list(set(c for a in group for c in a.get("category_hint", [])))

        primary["duplicate_sources"] = all_sources
        primary["category_hint"] = all_categories
        primary["source_count"] = len(all_sources)  # 被多少源报道

        return primary
