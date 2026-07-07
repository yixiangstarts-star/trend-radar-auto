"""IMA OpenAPI 客户端：笔记创建、追加、搜索

API 接口（已验证）：
- 创建笔记：POST openapi/note/v1/import_doc
- 追加笔记：POST openapi/note/v1/append_doc
- 认证方式：Header 中携带 X-IMA-Client-Id 和 X-IMA-Api-Key
"""

import logging
import json
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)


class IMAClient:
    """IMA 知识库 API 客户端"""

    def __init__(self, base_url: str, client_id: str, api_key: str):
        """
        Args:
            base_url: IMA API基础地址，如 https://ima.qq.com
            client_id: IMA Client ID
            api_key: IMA API Key
        """
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.api_key = api_key
        self.session = requests.Session()

        # 认证头（IMA OpenAPI 官方格式）
        self.session.headers.update({
            "Content-Type": "application/json",
            "ima-openapi-clientid": client_id,
            "ima-openapi-apikey": api_key,
        })

    # ========== 笔记操作 ==========

    def create_note(self, content: str, folder_id: str = "") -> Optional[str]:
        """创建新笔记

        Args:
            content: Markdown格式的笔记内容
            folder_id: 可选，目标笔记本ID

        Returns:
            成功返回 note_id，失败返回 None
        """
        url = f"{self.base_url}/openapi/note/v1/import_doc"

        payload = {
            "content": content,
            "content_format": 1,  # 1 = Markdown
        }
        if folder_id:
            payload["folder_id"] = folder_id

        try:
            resp = self.session.post(url, json=payload, timeout=30)
            data = resp.json()

            # IMA 返回格式: {"code": 0, "msg": "success", "data": {"note_id": "xxx"}}
            if resp.status_code == 200 and data.get("code") == 0:
                note_id = data.get("data", {}).get("note_id")
                if note_id:
                    logger.info(f"笔记创建成功: {note_id}")
                    return note_id
                else:
                    logger.warning(f"响应成功但无 note_id: {data}")
                    return None
            else:
                logger.error(f"创建笔记失败 [{resp.status_code}]: {data}")
                return None

        except requests.RequestException as e:
            logger.error(f"创建笔记请求异常: {e}")
            return None

    def append_note(self, note_id: str, content: str) -> bool:
        """追加内容到已有笔记

        Args:
            note_id: 目标笔记ID
            content: Markdown格式的追加内容

        Returns:
            成功返回 True
        """
        url = f"{self.base_url}/openapi/note/v1/append_doc"

        # 单次写入大小限制检查（IMA约10MB，但一般Markdown不会超）
        if len(content.encode("utf-8")) > 10 * 1024 * 1024:
            logger.error("内容超过10MB限制，请拆分写入")
            return False

        payload = {
            "note_id": note_id,
            "content": content,
            "content_format": 1,
        }

        try:
            resp = self.session.post(url, json=payload, timeout=30)
            data = resp.json()

            if resp.status_code == 200 and data.get("code") == 0:
                logger.info(f"笔记追加成功: {note_id}")
                return True
            else:
                logger.error(f"追加笔记失败 [{resp.status_code}]: {data}")
                return False

        except requests.RequestException as e:
            logger.error(f"追加笔记请求异常: {e}")
            return False

    # ========== 便捷方法 ==========

    def create_daily_report(self, content: str, date_str: str = "") -> Optional[str]:
        """创建每日日报笔记

        Args:
            content: Markdown格式的日报内容
            date_str: 日期字符串（如 2026-07-06），用于标题

        Returns:
            成功返回 note_id
        """
        title = f"# 📊 科技日报 {date_str}\n\n" if date_str else "# 📊 科技日报\n\n"
        full_content = title + content

        return self.create_note(full_content)

    def append_to_category_note(self, category_note_id: str, articles_md: str) -> bool:
        """追加内容到分类笔记

        Args:
            category_note_id: 分类笔记ID
            articles_md: Markdown格式的文章列表
        """
        # 添加分隔线
        content = f"\n---\n\n{articles_md}\n"
        return self.append_note(category_note_id, content)

    def batch_append_categories(
        self, category_notes: Dict[str, str], categorized_articles: Dict[str, str]
    ) -> Dict[str, bool]:
        """批量追加到各分类笔记

        Args:
            category_notes: {"C01": "note_id_xxx", ...}
            categorized_articles: {"C01": "markdown内容", ...}

        Returns:
            {"C01": True/False, ...}
        """
        results = {}
        for cat_code, content in categorized_articles.items():
            note_id = category_notes.get(cat_code)
            if not note_id:
                logger.warning(f"分类 {cat_code} 未配置笔记ID，跳过")
                results[cat_code] = False
                continue

            results[cat_code] = self.append_to_category_note(note_id, content)

        return results

    def check_connection(self) -> bool:
        """测试API连接是否正常"""
        try:
            # 尝试一个简单的API调用
            url = f"{self.base_url}/openapi/note/v1/import_doc"
            payload = {
                "content": "# 连接测试",
                "content_format": 1,
            }
            resp = self.session.post(url, json=payload, timeout=10)
            return resp.status_code in (200, 401)  # 200或401都说明服务可达
        except Exception:
            return False
