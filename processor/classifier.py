"""分类模块：基于关键词的新闻自动分类"""

import logging
import re
from typing import List, Dict

logger = logging.getLogger(__name__)

# 8大分类关键词库
CATEGORY_KEYWORDS = {
    "C01": {  # AI与大模型
        "AI", "人工智能", "大模型", "GPT", "ChatGPT", "LLM", "深度学习",
        "神经网络", "NLP", "Transformer", "生成式AI", "AIGC", "机器学习",
        "OpenAI", "DeepMind", "Claude", "Gemini", "文心一言", "通义千问",
        "混元", "星火", "Agent", "智能体", "多模态", "Sora", "视频生成",
        "AI芯片", "NPU", "算力", "推理", "训练", "微调", "对齐",
    },
    "C02": {  # 芯片与半导体
        "芯片", "半导体", "CPU", "GPU", "英伟达", "NVIDIA", "AMD",
        "英特尔", "Intel", "高通", "台积电", "三星", "EUV", "光刻",
        "制程", "纳米", "芯片设计", "RISC-V", "ARM", "EDA",
        "封装", "晶圆", "流片", "Rubin", "Blackwell", "Hopper",
    },
    "C03": {  # 智能汽车与新能源
        "智能汽车", "电动车", "新能源", "特斯拉", "蔚来", "小鹏",
        "理想", "比亚迪", "自动驾驶", "FSD", "NOA", "激光雷达",
        "电池", "固态电池", "充电", "换电", "车联网", "智能座舱",
    },
    "C04": {  # 互联网平台与产品
        "微信", "抖音", "快手", "小红书", "B站", "知乎", "微博",
        "百度", "阿里", "腾讯", "字节", "美团", "京东", "拼多多",
        "小程序", "电商", "社交", "直播", "视频号", "应用商店",
        "互联网", "平台", "产品", "APP", "上线", "更新", "改版",
    },
    "C05": {  # 创投与融资
        "融资", "投资", "IPO", "上市", "估值", "天使轮", "A轮",
        "B轮", "C轮", "VC", "PE", "风投", "创投", "红杉",
        "收购", "并购", "退出", "基金", "独角兽", "创业",
    },
    "C06": {  # 硬件与消费电子
        "手机", "iPhone", "华为", "小米", "OPPO", "vivo", "三星",
        "电脑", "笔记本", "平板", "iPad", "Mac", "Windows",
        "耳机", "手表", "手环", "AR", "VR", "MR", "Vision Pro",
        "无人机", "相机", "显示器", "键盘", "鼠标", "硬件",
        "消费电子", "开箱", "评测", "数码", "可穿戴", "机器人",
    },
    "C07": {  # 科技政策与监管
        "监管", "政策", "法规", "反垄断", "数据安全", "隐私",
        "审查", "合规", "禁止", "限制", "许可", "牌照",
        "工信部", "网信办", "发改委", "欧盟", "GDPR", "AI法案",
    },
    "C08": {  # 开源与技术工具
        "开源", "GitHub", "Git", "Docker", "Kubernetes", "Linux",
        "Python", "Rust", "Go", "JavaScript", "API", "框架",
        "开发", "代码", "编译器", "IDE", "工具", "插件",
        "云计算", "云原生", "Serverless", "DevOps", "CI/CD",
    },
}


class Classifier:
    """新闻自动分类器

    策略：
    1. 优先使用RSS源配置的 category_hint
    2. 关键词匹配补充分类
    3. 无匹配时归入 C04（互联网平台，覆盖面最广）
    """

    def __init__(self, categories: Dict[str, str] = None):
        """
        Args:
            categories: 分类名称映射 {"C01": "AI与大模型", ...}
        """
        self.categories = categories or {}
        self.keywords = CATEGORY_KEYWORDS

    def classify(self, articles: List[Dict]) -> List[Dict]:
        """对所有新闻进行分类"""
        for article in articles:
            categories = self._classify_one(article)
            article["categories"] = categories
            article["category_names"] = [
                self.categories.get(c, c) for c in categories
            ]
        return articles

    def _classify_one(self, article: Dict) -> List[str]:
        """对单篇新闻分类，返回分类代码列表"""
        text = f"{article.get('title', '')} {article.get('summary', '')}"
        text_lower = text.lower()

        scores = {}

        # 1. RSS源配置的分类提示（权重=2）
        for hint in article.get("category_hint", []):
            scores[hint] = scores.get(hint, 0) + 2

        # 2. 关键词匹配
        for cat_code, keywords in self.keywords.items():
            for kw in keywords:
                if kw.lower() in text_lower:
                    scores[cat_code] = scores.get(cat_code, 0) + 1

        # 3. 选择得分最高的分类（最多2个）
        if not scores:
            return ["C04"]  # 默认归入互联网平台

        sorted_cats = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        result = [sorted_cats[0][0]]

        # 如果第二高分 >= 第一高分的60%，也加入
        if len(sorted_cats) > 1 and sorted_cats[1][1] >= sorted_cats[0][1] * 0.6:
            result.append(sorted_cats[1][0])

        return result

    def group_by_category(self, articles: List[Dict]) -> Dict[str, List[Dict]]:
        """按主分类分组"""
        groups = {}
        for article in articles:
            main_cat = article.get("categories", ["C04"])[0]
            if main_cat not in groups:
                groups[main_cat] = []
            groups[main_cat].append(article)
        return groups
