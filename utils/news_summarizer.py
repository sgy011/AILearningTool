import logging
import os
import time
from typing import Dict, List, Optional

from openai import OpenAI

from utils.openai_compat import get_openai_compat_config
from utils.text_format import (
    normalize_display_text,
    normalize_title,
    truncate_preserving_readability,
)
from utils.softunis_scraper import scrape_softunis_channel, softunis_list_url_for_tag
from utils.tencent_news_scraper import scrape_tencent_channel

logger = logging.getLogger(__name__)

class NewsSummarizer:
    """软盟资讯 AI 列表 / 腾讯新闻频道列表抓取 + AI 总结（网页与公开接口，不经商业新闻 API）"""

    def __init__(self, modelscope_token: str = None, base_url: str = None):
        cfg = get_openai_compat_config()
        # 兼容旧参数：若显式传入仍优先使用（主要给 tests/调用方）
        api_key = (modelscope_token or "").strip() or cfg.api_key
        base = (base_url or "").strip() or cfg.base_url
        self.modelscope_token = api_key
        self.base_url = base
        # 正文摘要上限（汉字约等于字）；完成 token 略大于字数即可
        self.summary_max_chars = max(100, min(int(os.getenv("NEWS_SUMMARY_MAX_CHARS", "500")), 4000))
        self.summary_max_tokens = int(os.getenv("NEWS_SUMMARY_MAX_TOKENS", "1024"))

        self.client = None
        if self.modelscope_token:
            try:
                self.client = OpenAI(base_url=self.base_url, api_key=self.modelscope_token)
            except Exception as e:
                logger.warning("OpenAI 客户端初始化失败：%s", e)
                self.client = None

    def is_configured(self) -> Dict[str, bool]:
        return {
            "ai_api": bool(self.modelscope_token and self.client),
        }

    def _truncate_summary_text(self, text: str, *, max_chars: Optional[int] = None) -> str:
        """模型偶发超长时截断到配置字数；尽量在句读/换行处截断，少切断关键尾信息。"""
        t = (text or "").strip()
        cap = max_chars if max_chars is not None else self.summary_max_chars
        cap = max(100, min(int(cap), 12000))
        return truncate_preserving_readability(t, cap, ellipsis="…")

    def _summary_fallback_body(self, article: Dict) -> str:
        """无 AI 或总结失败时，用已抓取正文/摘要填充展示区（热榜常无 description）。"""
        return normalize_display_text(
            (article.get("content") or article.get("description") or "").strip(),
            multiline=True,
        )

    def summarize_article(self, article: Dict) -> str:
        if not self.client:
            logger.warning("[总结] 未配置 API Key，展示抓取正文（非 AI 总结）")
            fb = self._summary_fallback_body(article)
            if fb:
                return fb
            return "未配置 AI 且未抓取到正文，请设置 API Key 或稍后重试。"

        try:
            content = article.get("content") or article.get("description") or ""
            title_preview = (article.get("title") or "")[:80]
            mc = self.summary_max_chars
            logger.info(
                "[总结] 请求开始 title=%r 输入约 %d 字 max_chars=%s max_tokens=%s",
                title_preview,
                len(content),
                mc,
                self.summary_max_tokens,
            )
            t0 = time.perf_counter()
            prompt = f"""请仅根据下方「文章内容」用中文概括新闻要点。
要求：
1. 只总结正文信息，不要复述标题、不要重复来源/栏目/作者，不要写「本文」「综上所述」「文章来源」等套话。
2. 全文总结不超过 {mc} 字（汉字按字计数）；语言简洁、可分条或短段落。
3. 信息不足时据实简短概括，不要编造。
4. 标题与来源仅供理解上下文，不要单独成段输出。
5. 保留关键可核对信息：数字、日期与时间、金额、百分比、统计口径、专有名词、人物/地名/机构名等尽量准确写出；使用规范中文标点（句号、逗号、顿号、分号、书名号、引号等）分段表意，不要随意删改标点或合并词句导致歧义。

文章标题（仅供理解，勿复述）：{article.get('title', '')}
来源（仅供理解）：{article.get('source', '')}
文章内容：
{content}
"""

            response = self.client.chat.completions.create(
                model="moonshotai/Kimi-K2.5",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=self.summary_max_tokens,
            )
            raw_msg = (response.choices[0].message.content or "").strip()
            summary = normalize_display_text(raw_msg, multiline=True, summary_output=True)
            summary = self._truncate_summary_text(summary, max_chars=self.summary_max_chars)
            if not summary:
                logger.warning("[总结] 模型返回为空，改用正文兜底 title=%r", title_preview)
                summary = self._summary_fallback_body(article)
            elapsed = time.perf_counter() - t0
            usage = getattr(response, "usage", None)
            if usage is not None:
                pt = getattr(usage, "prompt_tokens", None)
                ct = getattr(usage, "completion_tokens", None)
                tt = getattr(usage, "total_tokens", None)
                logger.info(
                    "[总结] 完成 输出约 %d 字 耗时 %.2fs tokens prompt=%s completion=%s total=%s",
                    len(summary),
                    elapsed,
                    pt,
                    ct,
                    tt,
                )
            else:
                logger.info(
                    "[总结] 完成 输出约 %d 字 耗时 %.2fs（无 usage 字段）",
                    len(summary),
                    elapsed,
                )
            return summary
        except Exception as e:
            logger.error("[总结] 异常：%s", e, exc_info=True)
            fb = self._summary_fallback_body(article)
            if fb:
                return fb
            return "AI 总结失败且暂无正文可展示，请查看日志或阅读原文。"

    def summarize_articles_combined(self, articles: List[Dict], *, use_ai: bool) -> str:
        """
        多篇资讯合并为一段输出（无 AI 时拼接各篇正文摘录）。
        链接由前端/调用方单独附在文末，提示模型勿输出 URL。
        """
        if not articles:
            return ""
        n = len(articles)
        cap = min(max(self.summary_max_chars * 2, 600), 4000)

        if not use_ai or not self.client:
            parts: List[str] = []
            for a in articles:
                t = normalize_title(a.get("title", "") or "")
                body = self._summary_fallback_body(a)
                if len(body) > 1200:
                    body = body[:1199].rstrip() + "…"
                parts.append(f"【{t}】\n{body}" if t else body)
            merged = normalize_display_text("\n\n".join(parts), multiline=True)
            return self._truncate_summary_text(merged, max_chars=min(12000, 1500 * max(n, 1)))

        blocks: List[str] = []
        for i, a in enumerate(articles, 1):
            title = (a.get("title") or "").strip()
            raw = (a.get("content") or a.get("description") or "").strip()
            excerpt = raw[:2200] + ("…" if len(raw) > 2200 else "")
            blocks.append(f"### 报道{i}\n标题：{title}\n正文摘录：\n{excerpt}\n")
        corpus = "\n".join(blocks)

        try:
            prompt = f"""以下共 {n} 条资讯摘录，请用中文写一份**合并简报**（一整段阅读体验，不要拆成多篇独立小作文）。
要求：
1. 提炼跨条目的要点，可用简短小标题或分条，但不要逐条复述原文。
2. 全文不超过 {cap} 字（汉字按字计）；语言简洁。
3. 信息不足时据实简短概括，不要编造。
4. **不要**输出任何 URL、链接、「点击」「阅读原文」等；不要复述来源网站名称作套话。
5. 各条中的数字、日期、金额、百分比、专名与地名/机构名须尽量保留且准确；标点清晰（句号、逗号、顿号、分号、书名号、引号等），避免因过度压缩或乱用空格导致信息含糊。

{corpus}
"""
            t0 = time.perf_counter()
            response = self.client.chat.completions.create(
                model="moonshotai/Kimi-K2.5",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.35,
                max_tokens=min(self.summary_max_tokens * 2, 4096),
            )
            raw_msg = (response.choices[0].message.content or "").strip()
            summary = normalize_display_text(raw_msg, multiline=True, summary_output=True)
            summary = self._truncate_summary_text(summary, max_chars=cap)
            if not summary:
                return self.summarize_articles_combined(articles, use_ai=False)
            logger.info(
                "[总结] 合并简报完成 约 %d 字 耗时 %.2fs",
                len(summary),
                time.perf_counter() - t0,
            )
            return summary
        except Exception as e:
            logger.error("[总结] 合并简报异常：%s", e, exc_info=True)
            return self.summarize_articles_combined(articles, use_ai=False)

    def _article_stubs(self, articles: List[Dict]) -> List[Dict]:
        """列表展示用：标题/链接/元信息，不含逐篇 summary。"""
        out: List[Dict] = []
        for article in articles:
            item: Dict = {
                "title": normalize_title(article.get("title", "")),
                "url": article.get("url", ""),
                "summary": "",
                "description": normalize_display_text(
                    article.get("description", ""),
                    multiline=True,
                ),
                "published_at": article.get("published_at", ""),
                "source": article.get("source", ""),
                "author": article.get("author", ""),
                "image_url": article.get("image_url", ""),
                "source_type": article.get("source_type", ""),
            }
            if article.get("hot_rank") is not None:
                try:
                    item["hot_rank"] = int(article["hot_rank"])
                except (TypeError, ValueError):
                    pass
            if article.get("hot_label"):
                item["hot_label"] = str(article["hot_label"])
            out.append(item)
        return out

    def batch_summarize(self, articles: List[Dict], use_ai: bool = True) -> List[Dict]:
        summarized_articles = []
        batch_t0 = time.perf_counter()
        logger.info(
            "[总结] 批量开始 共 %d 篇 use_ai=%s client_ok=%s",
            len(articles),
            use_ai,
            bool(self.client),
        )
        for i, article in enumerate(articles):
            logger.info("[总结] 进度 %d/%d", i + 1, len(articles))
            if use_ai and self.client:
                summary = self.summarize_article(article)
            else:
                summary = self._summary_fallback_body(article)
                logger.info(
                    "[总结] 第 %d 篇未调用 AI，使用正文/摘要兜底 约 %d 字",
                    i + 1,
                    len(summary or ""),
                )
            out_item: Dict = {
                "title": normalize_title(article.get("title", "")),
                "url": article.get("url", ""),
                "summary": summary,
                "description": normalize_display_text(
                    article.get("description", ""),
                    multiline=True,
                ),
                "published_at": article.get("published_at", ""),
                "source": article.get("source", ""),
                "author": article.get("author", ""),
                "image_url": article.get("image_url", ""),
                "source_type": article.get("source_type", ""),
            }
            if article.get("hot_rank") is not None:
                try:
                    out_item["hot_rank"] = int(article["hot_rank"])
                except (TypeError, ValueError):
                    pass
            if article.get("hot_label"):
                out_item["hot_label"] = str(article["hot_label"])
            summarized_articles.append(out_item)
        logger.info(
            "[总结] 批量结束 耗时 %.2fs",
            time.perf_counter() - batch_t0,
        )
        return summarized_articles

    def search_and_summarize(
        self,
        limit: int = 10,
        use_ai: bool = True,
        toutiao_page_url: Optional[str] = None,
        feed: str = "softunis",
        qq_channel: Optional[str] = None,
        softunis_tag: Optional[str] = None,
    ) -> Dict:
        feed_norm = (feed or "softunis").strip().lower()
        if feed_norm not in ("softunis", "tencent"):
            feed_norm = "softunis"

        result: Dict = {
            "success": False,
            "message": "",
            "articles": [],
            "combined_summary": "",
            "total": 0,
            "config_status": self.is_configured(),
            "toutiao_scrape": False,
            "source": feed_norm,
            "qq_channel": (qq_channel or "").strip().lower() if feed_norm == "tencent" else None,
            "softunis_tag": (softunis_tag or "ai").strip().lower() if feed_norm == "softunis" else None,
        }

        try:
            _ = toutiao_page_url  # 兼容旧 POST 字段
            req_t0 = time.perf_counter()
            if feed_norm == "tencent":
                qch = (qq_channel or "tech").strip().lower()
                logger.info(
                    "[必读资讯] 任务开始 feed=tencent channel=%s limit=%s use_ai=%s",
                    qch,
                    limit,
                    use_ai,
                )
                try:
                    articles = scrape_tencent_channel(qch, limit=limit)
                except ValueError as e:
                    logger.warning("[必读资讯] 腾讯参数错误：%s", e)
                    result["message"] = str(e)
                    return result
                except Exception as e:
                    logger.exception("[必读资讯] 腾讯抓取异常")
                    result["message"] = f"腾讯新闻抓取失败：{str(e)}"
                    return result
            else:
                tag = (softunis_tag or "ai").strip().lower()
                page = softunis_list_url_for_tag(tag)
                logger.info(
                    "[必读资讯] 任务开始 feed=softunis tag=%s page=%s limit=%s use_ai=%s",
                    tag,
                    page,
                    limit,
                    use_ai,
                )
                try:
                    articles = scrape_softunis_channel(page, limit=limit)
                except ValueError as e:
                    logger.warning("[必读资讯] 参数错误：%s", e)
                    result["message"] = str(e)
                    return result
                except Exception as e:
                    logger.exception("[必读资讯] 抓取阶段异常")
                    result["message"] = f"软盟资讯抓取失败：{str(e)}"
                    return result

            scrape_elapsed = time.perf_counter() - req_t0
            logger.info(
                "[必读资讯] 抓取阶段结束 得到 %d 篇 耗时 %.2fs",
                len(articles),
                scrape_elapsed,
            )

            if not articles:
                result["message"] = "未抓取到可用文章"
                result["success"] = True
                logger.info("[必读资讯] 无可用文章，结束")
                return result

            config = self.is_configured()
            do_ai = bool(use_ai and config["ai_api"])
            if not do_ai:
                logger.info(
                    "[必读资讯] 未启用合并 AI 总结（use_ai=%s ai_api=%s）",
                    use_ai,
                    config.get("ai_api"),
                )
            result["combined_summary"] = self.summarize_articles_combined(
                articles,
                use_ai=do_ai,
            )
            result["ai_summarized"] = do_ai
            summarized = self._article_stubs(articles)

            result["success"] = True
            result["articles"] = summarized
            result["total"] = len(summarized)
            logger.info(
                "[必读资讯] 任务完成 共 %d 篇 总耗时 %.2fs",
                len(summarized),
                time.perf_counter() - req_t0,
            )
            return result

        except Exception as e:
            logger.error("[必读资讯] 处理失败：%s", e, exc_info=True)
            result["message"] = f"处理失败：{str(e)}"
            return result
