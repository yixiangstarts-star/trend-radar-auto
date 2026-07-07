"""科技新闻每日采集系统 - MVP 主流程

运行方式：
    python main.py                      # 手动运行
    python main.py --dry-run            # 试运行（不写IMA）
    python main.py --local-only         # 仅本地生成日报，不推IMA

环境变量（GitHub Actions）：
    IMA_CLIENT_ID       IMA Client ID
    IMA_API_KEY         IMA API Key
    IMA_KB_ID           IMA 知识库 ID
    WECHAT_WEBHOOK      企业微信 Webhook URL（可选）
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timezone, timedelta

import yaml

from collector.rss_collector import RSSCollector
from processor.dedup import Deduplicator
from processor.scorer import Scorer
from processor.classifier import Classifier
from processor.summarizer import Summarizer
from storage.ima_client import IMAClient
from storage.report_generator import ReportGenerator

# 北京时间
CST = timezone(timedelta(hours=8))

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


def load_config(config_path: str = "sources.yaml") -> dict:
    """加载配置文件"""
    if not os.path.exists(config_path):
        # GitHub Actions 中可能需要完整路径
        config_path = os.path.join(os.path.dirname(__file__), config_path)

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config


def run_pipeline(config: dict, args) -> dict:
    """执行采集流水线"""
    results = {}

    # ========== Step 1: 采集 ==========
    logger.info("=" * 50)
    logger.info("Step 1/5: 开始采集 RSS 新闻...")
    logger.info("=" * 50)

    collector = RSSCollector(
        sources=config["rss_sources"],
        lookback_hours=config["pipeline"]["lookback_hours"],
    )
    articles = collector.collect_all()

    if not articles:
        logger.warning("未采集到任何新闻！")
        return {"status": "empty", "articles": []}

    logger.info(f"采集完成，共 {len(articles)} 篇原始新闻")
    results["raw_count"] = len(articles)

    # ========== Step 2: 去重 ==========
    logger.info("=" * 50)
    logger.info("Step 2/5: 去重...")
    logger.info("=" * 50)

    dedup = Deduplicator(threshold=config["pipeline"]["dedup_threshold"])
    articles = dedup.deduplicate(articles)

    logger.info(f"去重后 {len(articles)} 篇")
    results["dedup_count"] = len(articles)

    # ========== Step 3: 热度评分 ==========
    logger.info("=" * 50)
    logger.info("Step 3/5: 热度评分...")
    logger.info("=" * 50)

    scorer = Scorer()
    articles = scorer.score(articles)
    results["heat_distribution"] = {
        lv: sum(1 for a in articles if a.get("heat_level") == lv)
        for lv in ["S", "A", "B", "C"]
    }

    # ========== Step 4: 分类 + 摘要 ==========
    logger.info("=" * 50)
    logger.info("Step 4/5: 分类 + 生成摘要...")
    logger.info("=" * 50)

    classifier = Classifier(categories=config["pipeline"]["categories"])
    articles = classifier.classify(articles)

    summarizer = Summarizer()
    top_n = config["pipeline"]["top_n_summary"]
    articles = summarizer.generate(articles, top_n=top_n)

    # ========== Step 5: 生成日报 + IMA入库 ==========
    logger.info("=" * 50)
    logger.info("Step 5/5: 生成日报 + IMA 入库...")
    logger.info("=" * 50)

    # 生成日报
    report_gen = ReportGenerator(categories=config["pipeline"]["categories"])
    report = report_gen.generate_daily_report(articles)

    # 保存到本地
    output_dir = config["pipeline"].get("output_dir", "./output")
    os.makedirs(output_dir, exist_ok=True)
    today = datetime.now(CST).strftime("%Y-%m-%d")
    report_path = os.path.join(output_dir, f"{today}-科技日报.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    logger.info(f"日报已保存到: {report_path}")
    results["report_path"] = report_path
    results["report"] = report[:500] + "..." if len(report) > 500 else report

    # IMA 入库
    if not args.dry_run and not args.local_only:
        ima_success = upload_to_ima(config, articles, report, today)
        results["ima_upload"] = ima_success
    else:
        if args.dry_run:
            logger.info("🔍 试运行模式，跳过 IMA 入库")
        else:
            logger.info("📁 仅本地模式，日报已保存")
        results["ima_upload"] = "skipped"

    results["status"] = "success"
    results["articles"] = articles
    return results


def upload_to_ima(config: dict, articles: list, report: str, date_str: str) -> dict:
    """上传日报到IMA知识库"""
    ima_config = config["ima"]

    # 从环境变量或配置文件获取凭证
    client_id = os.getenv("IMA_CLIENT_ID") or ima_config.get("client_id", "")
    api_key = os.getenv("IMA_API_KEY") or ima_config.get("api_key", "")

    if client_id == "YOUR_CLIENT_ID" or not client_id:
        logger.warning("⚠️  未配置 IMA 凭证，跳过入库。请在 sources.yaml 或环境变量中设置。")
        return {"status": "no_credentials"}

    logger.info("正在连接 IMA...")

    ima = IMAClient(
        base_url=ima_config["base_url"],
        client_id=client_id,
        api_key=api_key,
    )

    # 检查连接
    if not ima.check_connection():
        logger.error("❌ IMA 连接失败，请检查凭证和网络")
        return {"status": "connection_failed"}

    result = {"status": "partial", "daily_report": False, "categories": {}}

    # 1. 创建日报笔记
    logger.info("正在创建日报笔记...")
    note_id = ima.create_daily_report(report, date_str=date_str)
    if note_id:
        logger.info(f"✅ 日报笔记创建成功: {note_id}")
        result["daily_report"] = True
        result["daily_note_id"] = note_id
    else:
        logger.error("❌ 日报笔记创建失败")

    # 2. 按分类追加到各分类笔记
    logger.info("正在追加分类笔记...")
    category_notes = ima_config.get("category_notes", {})
    classifier = Classifier(categories=config["pipeline"]["categories"])
    groups = classifier.group_by_category(articles)

    report_gen = ReportGenerator(categories=config["pipeline"]["categories"])
    categorized_md = {}
    for cat_code, cat_articles in groups.items():
        md = report_gen.generate_category_markdown(cat_code, cat_articles, date_str)
        if md:
            categorized_md[cat_code] = md

    if categorized_md:
        cat_results = ima.batch_append_categories(category_notes, categorized_md)
        result["categories"] = cat_results
        success_count = sum(1 for v in cat_results.values() if v)
        logger.info(f"分类笔记追加: {success_count}/{len(cat_results)} 成功")
    else:
        logger.info("没有分类笔记需要追加")

    return result


def send_wechat_notification(config: dict, results: dict):
    """发送企业微信通知"""
    webhook = os.getenv("WECHAT_WEBHOOK") or config.get("notification", {}).get(
        "wechat_work_webhook", ""
    )

    if not webhook:
        logger.info("未配置企业微信 Webhook，跳过通知")
        return

    if results.get("status") != "success":
        return

    # 构造摘要消息
    today = datetime.now(CST).strftime("%Y年%m月%d日")
    dist = results.get("heat_distribution", {})
    raw = results.get("raw_count", 0)
    dedup = results.get("dedup_count", 0)

    msg = f"""📊 {today} 科技日报已生成

📥 采集 {raw} 篇 → 去重后 {dedup} 篇
🔥 S级 {dist.get('S', 0)} | A级 {dist.get('A', 0)} | B级 {dist.get('B', 0)} | C级 {dist.get('C', 0)}

📖 打开 IMA 知识库查看完整日报"""

    try:
        import requests

        payload = {
            "msgtype": "markdown",
            "markdown": {"content": msg},
        }
        resp = requests.post(webhook, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info("✅ 企业微信通知已发送")
        else:
            logger.warning(f"企业微信通知失败: {resp.text}")
    except Exception as e:
        logger.error(f"发送通知异常: {e}")


def main():
    parser = argparse.ArgumentParser(description="科技新闻每日采集系统 MVP")
    parser.add_argument("--dry-run", action="store_true", help="试运行，不写IMA")
    parser.add_argument("--local-only", action="store_true", help="仅本地生成日报")
    parser.add_argument("--config", default="sources.yaml", help="配置文件路径")
    args = parser.parse_args()

    logger.info("🚀 科技新闻每日采集系统 MVP 启动")
    logger.info(f"⏰ 北京时间: {datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')}")

    # 加载配置
    config = load_config(args.config)
    logger.info(f"📋 已加载 {len(config['rss_sources'])} 个 RSS 源")

    # 执行流水线
    results = run_pipeline(config, args)

    # 发送通知
    if results.get("status") == "success":
        logger.info("✅ 流水线执行完成！")
        send_wechat_notification(config, results)
    elif results.get("status") == "empty":
        logger.warning("⚠️  未采集到新闻，可能是源异常或网络问题")
    else:
        logger.error("❌ 流水线执行异常")

    return 0 if results.get("status") == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
