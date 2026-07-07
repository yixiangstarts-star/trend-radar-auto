"""热度评分模块：多维度新闻热度评估"""

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict

logger = logging.getLogger(__name__)

CST = timezone(timedelta(hours=8))


class Scorer:
    """新闻热度评分器

    评分模型：
    热度分 = 基础分 + 媒体权威分 - 时间衰减分

    热度等级：
    - S级 (🔥🔥🔥): >= 200
    - A级 (🔥🔥):   120-199
    - B级 (🔥):     60-119
    - C级 (·):     < 60
    """

    # 热度等级阈值
    LEVELS = [
        ("S", 200, "🔥🔥🔥"),
        ("A", 120, "🔥🔥"),
        ("B", 60,  "🔥"),
        ("C", 0,   "·"),
    ]

    def __init__(self):
        pass

    def score(self, articles: List[Dict]) -> List[Dict]:
        """对所有新闻进行热度评分"""
        now = datetime.now(CST)

        for article in articles:
            # 1. 基础分：被多少源报道 × 10
            source_count = article.get("source_count", 1)
            base_score = source_count * 10

            # 2. 媒体权威分
            authority = article.get("authority_score", 5)

            # 3. 时间衰减分
            published = article.get("published")
            if isinstance(published, str):
                published = datetime.fromisoformat(published)
            if published is None:
                published = now
            if published.tzinfo is None:
                published = published.replace(tzinfo=CST)

            hours_ago = max(0, (now - published).total_seconds() / 3600)
            time_decay = max(0, 100 - hours_ago * 5)

            # 总分
            total = base_score + authority + time_decay

            # 等级
            level, level_emoji = "C", "·"
            for lv, threshold, emoji in self.LEVELS:
                if total >= threshold:
                    level = lv
                    level_emoji = emoji
                    break
                # Note: LEVELS is sorted descending, so we break on first match

            # 修正：从高到低匹配
            if total >= 200:
                level, level_emoji = "S", "🔥🔥🔥"
            elif total >= 120:
                level, level_emoji = "A", "🔥🔥"
            elif total >= 60:
                level, level_emoji = "B", "🔥"
            else:
                level, level_emoji = "C", "·"

            article["heat_score"] = round(total, 1)
            article["heat_level"] = level
            article["heat_emoji"] = level_emoji
            article["score_detail"] = {
                "base": base_score,
                "authority": authority,
                "time_decay": round(time_decay, 1),
                "hours_ago": round(hours_ago, 1),
            }

        # 按热度分降序排列
        articles.sort(key=lambda x: x["heat_score"], reverse=True)

        # 统计
        stats = {}
        for a in articles:
            lv = a["heat_level"]
            stats[lv] = stats.get(lv, 0) + 1
        logger.info(f"热度分布: {stats}")

        return articles

    def get_top(self, articles: List[Dict], n: int = 10) -> List[Dict]:
        """获取Top N热度新闻"""
        return articles[:n]

    def get_by_level(self, articles: List[Dict], level: str) -> List[Dict]:
        """按热度等级筛选"""
        return [a for a in articles if a.get("heat_level") == level]
