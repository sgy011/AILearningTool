"""
抓取软盟资讯（WordPress）分类列表与文章正文，不经过第三方新闻 API。
列表页示例：https://news.softunis.com/ai
请遵守站点条款，控制频率与数量。
"""

from __future__ import annotations

import logging
import os
import re
import time
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

from utils.text_format import (
    normalize_display_text,
    normalize_from_html_fragment,
    normalize_title,
)

logger = logging.getLogger(__name__)

DEFAULT_SOFTUNIS_PAGE_URL = "https://news.softunis.com/ai"

# 软盟列表「AI 标签」→ 列表页 URL（扩展时在此追加）
SOFTUNIS_TAG_PAGES: List[Dict[str, str]] = [
    {"key": "ai", "label": "AI人工智能", "url": DEFAULT_SOFTUNIS_PAGE_URL},
]


def list_softunis_tag_options() -> List[Dict[str, str]]:
    """供前端下拉：仅返回 key / label，url 由服务端解析。"""
    return [{"key": t["key"], "label": t["label"]} for t in SOFTUNIS_TAG_PAGES]


def softunis_list_url_for_tag(tag_key: str) -> str:
    k = (tag_key or "ai").strip().lower()
    for t in SOFTUNIS_TAG_PAGES:
        if t["key"] == k:
            return t["url"]
    return DEFAULT_SOFTUNIS_PAGE_URL


_LIST_EXTRA_RE = re.compile(
    r"https://news\.softunis\.com/(\d+)\.html",
    re.IGNORECASE,
)


def _headers() -> Dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }


def _is_allowed_softunis_page_url(url: str) -> bool:
    try:
        p = urlparse((url or "").strip())
        if p.scheme not in ("http", "https"):
            return False
        host = (p.netloc or "").lower()
        return host in ("news.softunis.com", "www.news.softunis.com")
    except Exception:
        return False


def is_softunis_page_url(url: str) -> bool:
    """是否为软盟资讯站点下的列表/频道页 URL（用于与今日头条分流）。"""
    return _is_allowed_softunis_page_url(url)


class _EntryContentExtractor(HTMLParser):
    """提取首个 class 含 entry-content 的 div 内文本（按 div 深度配对）。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_target = False
        self._div_depth = 0
        self._skip_raw = 0  # script/style 嵌套深度
        self.parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        ad = dict(attrs)
        cls = (ad.get("class") or "") or ""
        if not self._in_target:
            if tag == "div" and "entry-content" in cls:
                self._in_target = True
                self._div_depth = 1
            return
        if self._skip_raw > 0:
            if tag in ("script", "style"):
                self._skip_raw += 1
            return
        if tag in ("script", "style"):
            self._skip_raw = 1
            return
        if tag == "div":
            self._div_depth += 1
        if tag == "br":
            self.parts.append("\n")
        elif tag in ("p", "h1", "h2", "h3", "h4", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._skip_raw > 0:
            if tag in ("script", "style"):
                self._skip_raw -= 1
            return
        if not self._in_target:
            return
        if tag in ("p", "div", "h1", "h2", "h3", "h4", "li", "ul", "ol"):
            self.parts.append("\n")
        if tag == "div":
            self._div_depth -= 1
            if self._div_depth <= 0:
                self._in_target = False

    def handle_data(self, data: str) -> None:
        if not self._in_target or self._skip_raw > 0:
            return
        if data and data.strip():
            self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


def _meta_content(html: str, prop: str) -> str:
    m = re.search(
        rf'(?:property|name)="{re.escape(prop)}"\s+content="([^"]*)"',
        html,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    m = re.search(
        rf'content="([^"]*)"\s+(?:property|name)="{re.escape(prop)}"',
        html,
        re.IGNORECASE,
    )
    return m.group(1).strip() if m else ""


def _extract_title(html: str) -> str:
    t = _meta_content(html, "og:title")
    if t:
        return t
    m = re.search(
        r'class="[^"]*entry-title[^"]*"[^>]*>([^<]+)',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        return normalize_title(m.group(1))
    m = re.search(r"<h1[^>]*>([^<]+)</h1>", html, re.IGNORECASE | re.DOTALL)
    return normalize_title(m.group(1)) if m else ""


def _extract_published(html: str) -> str:
    m = re.search(r'<time[^>]*datetime="([^"]+)"', html, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    t = _meta_content(html, "article:published_time")
    if t:
        return t
    return ""


def _extract_entry_html(html: str) -> str:
    """取 entry-content 内部 HTML 片段供 normalize_from_html_fragment。"""
    m = re.search(
        r'(?is)<div[^>]*class="[^"]*entry-content[^"]*"[^>]*>(.*)',
        html,
    )
    if not m:
        return ""
    # 粗略截断到 entry-footer、版权块、相关推荐、作者区之前，避免吞整页（取最早出现的块）
    rest = m.group(1)
    html_cut_patterns = (
        r'(?is)<(footer|div|section)[^>]*class="[^"]*(?:entry-footer|post-navigation|'
        r'post-related|article-related|entry-author|article-author|copyright|article-copyright|'
        r'post-copyright|author-box|widget-area)[^"]*"[^>]*>',
        r'(?is)<div[^>]*id="[^"]*(?:comments|respond)[^"]*"[^>]*>',
        r'(?is)<(footer|div)[^>]*class="[^"]*(?:entry-footer|post-navigation)[^"]*"[^>]*>',
    )
    cut_starts: List[int] = []
    for pat in html_cut_patterns:
        cut = re.search(pat, rest)
        if cut:
            cut_starts.append(cut.start())
    if cut_starts:
        rest = rest[: min(cut_starts)]
    return rest


# 版权声明起笔（含半角/全角冒号），其后整段不要
_SOFTUNIS_COPYRIGHT_HEAD_RE = re.compile(r"关于文章版权的声明\s*[：:]")

# 正文末尾常见的版权、互动、侧栏误入等标记（从首次出现处截断，保留真实新闻段落）
_SOFTUNIS_TEXT_CUT_MARKERS: tuple[str, ...] = (
    "若非本站原创的文章",
    "本文刊载所有内容仅供",
    "凡注明为其他媒体来源的信息",
    "如有未注明作者及出处的文章",
    "共同建设自媒体信息平台",
    "关于本文作者",
    "相关推荐",
    "发表回复",
    "生成海报",
    "请登录后评论",
)


def _trim_softunis_footer_text(text: str) -> str:
    """去除软盟文章页尾部版权说明、作者卡片、相关推荐、站点导航等噪声。"""
    if not text:
        return text
    t = text.strip()
    cut_at = len(t)
    m = _SOFTUNIS_COPYRIGHT_HEAD_RE.search(t)
    if m:
        cut_at = min(cut_at, m.start())
    for marker in _SOFTUNIS_TEXT_CUT_MARKERS:
        i = t.find(marker)
        if i != -1 and i < cut_at:
            cut_at = i
    # 「上一篇」「下一篇」多为文末导航（带日期/标题的长行）
    for m in re.finditer(r"[\n\r]+上一篇[\n\r]", t):
        if m.start() < cut_at:
            cut_at = m.start()
    for m in re.finditer(r"[\n\r]+下一篇[\n\r]", t):
        if m.start() < cut_at:
            cut_at = m.start()
    # 侧栏「文章分类」「热门文章」等常为独立标题行
    for m in re.finditer(r"[\n\r]+(?:文章分类|热门文章|文章归档|新闻投稿)[\n\r]", t):
        if m.start() < cut_at:
            cut_at = m.start()
    # 文末「赞 (n)」互动
    m = re.search(r"[\n\r]+赞\s*\(\d+\)\s*[\n\r]?", t)
    if m and m.start() < cut_at:
        cut_at = m.start()
    # 文末 URL +「文章来自软盟资讯」类版权行（常见于声明块）
    m = re.search(
        r"[\n\r]+https?://news\.softunis\.com/\d+\.html\s*文章来自软盟资讯",
        t,
        re.IGNORECASE,
    )
    if m and m.start() < cut_at:
        cut_at = m.start()

    out = t[:cut_at].strip()
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out


def _fingerprint_softunis_headline(s: str) -> str:
    """去空白与标点差异，用于比对「每日AI必读」标题与正文首行重复。"""
    t = s.casefold()
    t = re.sub(r"[\s\u3000:：,，.。、/\\\-（）()]+", "", t)
    return t


def _polish_softunis_body_text(text: str, title: str) -> str:
    """压缩行内多余空格；去掉与标题重复的导语行、软盟发布时间行（如「软盟资讯 15小时前」）。"""
    if not text:
        return text
    lines = [re.sub(r" {2,}", " ", ln.strip()) for ln in text.splitlines()]
    t = "\n".join(ln for ln in lines if ln).strip()
    if not t:
        return t
    lines = t.splitlines()
    tit_fp = _fingerprint_softunis_headline(title) if title else ""

    while lines:
        head = lines[0].strip()
        fp = _fingerprint_softunis_headline(head)
        if tit_fp and fp and len(fp) >= 12:
            if fp == tit_fp or fp in tit_fp or tit_fp in fp:
                lines.pop(0)
                continue
        if re.match(r"^软盟资讯\s+", head) and re.search(
            r"(小时前|分钟前|天前|秒前|刚刚|\d+\s*小时前)",
            head,
        ):
            lines.pop(0)
            continue
        break
    return "\n".join(lines).strip()


def fetch_article_page(url: str) -> Dict[str, Any]:
    r = requests.get(url, headers=_headers(), timeout=45)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    html = r.text
    title = _extract_title(html)
    image = _meta_content(html, "og:image")
    published = _extract_published(html)

    fragment = _extract_entry_html(html)
    content = ""
    if fragment:
        parser = _EntryContentExtractor()
        try:
            parser.feed(fragment)
            inner = parser.text()
            if inner.strip():
                content = normalize_display_text(inner, multiline=True)
        except Exception as e:
            logger.debug("[软盟] entry HTMLParser 失败，回退 strip: %s", e)
        if not content.strip():
            content = normalize_from_html_fragment(fragment)
    if not content.strip():
        desc = _meta_content(html, "og:description")
        content = normalize_display_text(desc, multiline=True)

    content = _trim_softunis_footer_text(content)
    ntitle = normalize_title(title)
    content = _polish_softunis_body_text(content, ntitle)

    abstract = (content or "")[:400]
    return {
        "title": ntitle,
        "url": url,
        "content": content,
        "description": abstract,
        "published_at": published,
        "source": "软盟资讯",
        "author": "",
        "image_url": image or "",
        "source_type": "softunis_scrape",
    }


def _collect_list_article_urls(html: str, limit: int) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for m in _LIST_EXTRA_RE.finditer(html):
        num = m.group(1)
        u = f"https://news.softunis.com/{num}.html"
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
        if len(out) >= limit * 3:
            break
    return out


def scrape_softunis_channel(
    page_url: Optional[str] = None,
    *,
    limit: int = 10,
    delay_sec: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    抓取软盟资讯列表页中的文章（默认 AI 分类 /ai），逐篇请求正文。
    """
    url = (page_url or "").strip() or DEFAULT_SOFTUNIS_PAGE_URL
    if not _is_allowed_softunis_page_url(url):
        raise ValueError("仅支持 news.softunis.com 下的频道页 URL")

    if delay_sec is None:
        delay_sec = float(os.getenv("NEWS_SCRAPE_DELAY_SEC", "0.4") or "0.4")

    limit = max(1, min(int(limit), 40))
    scrape_t0 = time.perf_counter()
    logger.info(
        "[软盟爬取] 开始 list_url=%s limit=%s delay_sec=%s",
        url,
        limit,
        delay_sec,
    )

    r = requests.get(url, headers=_headers(), timeout=45)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    list_urls = _collect_list_article_urls(r.text, limit)
    logger.info("[软盟爬取] 列表解析得到 %d 个候选链接", len(list_urls))

    articles: List[Dict[str, Any]] = []
    skipped_empty = 0
    for u in list_urls:
        if len(articles) >= limit:
            break
        try:
            art = fetch_article_page(u)
            if delay_sec > 0:
                time.sleep(delay_sec)
        except Exception as e:
            logger.warning("[软盟爬取] 文章页失败 url=%s: %s", u, e)
            continue
        if not (art.get("content") or "").strip():
            skipped_empty += 1
            continue
        articles.append(art)
        logger.info(
            "[软盟爬取] 第 %d 篇 OK 正文约 %d 字 title=%r",
            len(articles),
            len(art.get("content") or ""),
            (art.get("title") or "")[:60],
        )

    logger.info(
        "[软盟爬取] 结束 有效 %d 篇 跳过空正文=%d 总耗时 %.2fs",
        len(articles),
        skipped_empty,
        time.perf_counter() - scrape_t0,
    )
    return articles
