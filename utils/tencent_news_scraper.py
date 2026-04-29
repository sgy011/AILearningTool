"""
腾讯新闻：列表优先 PC 频道页（requests + 可选 Playwright + DOM/整页正则抽链）；
部分栏目（如要闻）可能无 rain 锚点时，可回退 pacaio.match.qq.com 列表（见 TENCENT_PACAI_FALLBACK）。
正文走 r.inews.qq.com/getSimpleNews。请遵守腾讯服务条款与 robots。
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import requests

from utils.text_format import (
    normalize_display_text,
    normalize_from_html_fragment,
    normalize_title,
)

# -----------------------------------------------------------------------------
# 合规与使用范围（本模块内声明，便于代码审计与自查；不构成法律意见）
#
# PERSONAL_USE_ONLY：语义开关。为 True 时，表示部署/运行本代码的意图为「个人学习、技术验证、
# 非商业化、合理频率、少量篇数」场景；不用于对外提供商业数据服务、不用于大规模自动化爬取、
# 不用于绕过访问控制或干扰腾讯服务正常运行。请同时遵守 https://news.qq.com/ 等服务条款与适用法律法规。
#
# 若改为 False：仅表示调用方自行承担全部合规责任；建议在修改前确认已获得合法数据授权。
# 本仓库作者不对任何滥用行为负责。
# -----------------------------------------------------------------------------
PERSONAL_USE_ONLY = True

logger = logging.getLogger(__name__)

# robots.txt 解析缓存（频道页列表路径用；失败则视为不限制，避免反复请求）
_robots_parser_cache: Optional[RobotFileParser] = None
_robots_parser_tried: bool = False

# 下拉选项 key -> (展示名, chlid)；chlid 仅兼容 API/前端展示，列表抓取不调用 pacaio
QQ_NEWS_CHANNELS: Dict[str, Tuple[str, str]] = {
    # key 仍为 politics 兼容旧 API；展示为「要闻」，列表页 ch/yaowen，pacaio 用 news_news_top（要闻页内嵌字段）
    "politics": ("要闻", "news_news_top"),
    "tech": ("科技", "news_news_tech"),
    "kepu": ("科学", "news_news_kepu"),
    "sports": ("体育", "news_news_sports"),
}

# 与频道对应的 PC 列表页主 URL（与科技/体育等一致：news.qq.com/ch/{name}/）
QQ_CHANNEL_WARM_URL: Dict[str, str] = {
    "politics": "https://news.qq.com/ch/yaowen/",
    "tech": "https://news.qq.com/ch/tech/",
    "kepu": "https://news.qq.com/ch/kepu/",
    "sports": "https://news.qq.com/ch/sports/",
}

SIMPLE_NEWS_URL = "https://r.inews.qq.com/getSimpleNews"
PACAI_LIST_URL = "https://pacaio.match.qq.com/xw/site"
# PC 要闻页（ch/yaowen）实际拉取的榜单 JSON，静态 HTML 与 DOM 常无 /rain/a/ 链接
INEWS_PC_HOT_RANK_URL = "https://i.news.qq.com/gw/event/pc_hot_ranking_list"

_ARTICLE_ID_RE = re.compile(r"^20\d{6}[A-Z][A-Z0-9]*$")

# 频道页首屏链接不足时，尝试用浏览器渲染（与常见 PC 频道页结构一致；需可选依赖 playwright）
_TENCENT_CHANNEL_MIN_URLS_FOR_REQUESTS = 30
_TENCENT_PLAYWRIGHT_WAIT_MS = 4000
_TENCENT_PLAYWRIGHT_LOAD_MORE_ROUNDS = 3

_RAIN_ARTICLE_URL_RES = (
    re.compile(r"(?:https?:)?//(?:news|new)\.qq\.com/rain/a/([A-Za-z0-9]+)", re.I),
)
# 转义 JSON、内联脚本中的 rain 路径（无 http 前缀）
_RAIN_ESCAPED_PATH = re.compile(
    r'(?:\\\\?/|/)rain(?:\\\\?/|/)a(?:\\\\?/|/)(20\d{6}[A-Z][A-Z0-9]+)', re.I
)


def _walk_collect_list_items(obj: Any, found: List[Dict[str, str]]) -> None:
    """从 pacaio JSON 任意嵌套结构中收集 id+title。"""
    if isinstance(obj, dict):
        nid = obj.get("id") or obj.get("news_id") or obj.get("article_id") or obj.get("cmsid")
        title = obj.get("title") or obj.get("tl") or ""
        if isinstance(nid, str) and _ARTICLE_ID_RE.match(nid):
            tit = (title if isinstance(title, str) else "") or ""
            found.append({"id": nid, "title": tit.strip()})
        for v in obj.values():
            _walk_collect_list_items(v, found)
    elif isinstance(obj, list):
        for x in obj:
            _walk_collect_list_items(x, found)


def _dedupe_preserve_order(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen: set[str] = set()
    out: List[Dict[str, str]] = []
    for it in items:
        iid = it.get("id") or ""
        if not iid or iid in seen:
            continue
        seen.add(iid)
        out.append(it)
    return out


def list_qq_channel_options() -> List[Dict[str, str]]:
    """供前端 / API 返回频道列表。"""
    return [
        {"key": k, "label": v[0], "chlid": v[1]}
        for k, v in QQ_NEWS_CHANNELS.items()
    ]


def _headers(*, referer: str = "https://news.qq.com/") -> Dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": referer,
        "Origin": "https://news.qq.com",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
        "Connection": "keep-alive",
    }


def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_headers())
    return s


def _warm_channel_page(session: requests.Session, channel_key: str) -> None:
    """占位，避免仍调用旧接口时出现 NameError；频道页已由 _fetch_channel_page_article_list 请求。"""
    _ = (session, channel_key)


def _session_prefetch_news_home(session: requests.Session) -> None:
    """先访问腾讯新闻首页 https://news.qq.com/ ，与浏览器一致，利于 Cookie/跳转（各频道同一前置）。"""
    try:
        session.get(
            "https://news.qq.com/",
            headers=_document_headers(referer="https://www.qq.com/"),
            timeout=22,
        )
        _delay(0.2, 0.1)
    except Exception as e:
        logger.debug("[腾讯] news.qq.com 首页预热忽略: %s", e)


def _channel_try_urls(channel_key: str) -> List[str]:
    """各频道仅使用 news.qq.com 下列表页主 URL（无效镜像已移除）。"""
    primary = (QQ_CHANNEL_WARM_URL.get(channel_key) or "").strip()
    return [primary] if primary else []


def _delay(base: float, jitter: float) -> None:
    if base <= 0 and jitter <= 0:
        return
    extra = random.uniform(0, max(jitter, 0))
    time.sleep(base + extra)


def _qq_news_robots_parser() -> Optional[RobotFileParser]:
    global _robots_parser_cache, _robots_parser_tried
    if _robots_parser_tried:
        return _robots_parser_cache
    _robots_parser_tried = True
    parser = RobotFileParser()
    parser.set_url(urljoin("https://news.qq.com", "/robots.txt"))
    try:
        parser.read()
        _robots_parser_cache = parser
    except Exception:
        _robots_parser_cache = None
    return _robots_parser_cache


def _robots_allows(url: str) -> bool:
    p = _qq_news_robots_parser()
    if p is None:
        return True
    try:
        return p.can_fetch(_headers()["User-Agent"], url)
    except Exception:
        return True


def _extract_article_urls_from_channel_html(channel_html: str) -> List[str]:
    """从频道页 HTML 抽取候选文章链接（与常见腾讯 PC 频道页 URL 形态一致）。"""
    urls: List[str] = []
    seen: set[str] = set()
    patterns = [
        r"https?://news\.qq\.com/rain/a/[A-Za-z0-9]+",
        r"https?://new\.qq\.com/rain/a/[A-Za-z0-9]+",
        r"//news\.qq\.com/rain/a/[A-Za-z0-9]+",
        r"//new\.qq\.com/rain/a/[A-Za-z0-9]+",
        r"https?://new\.qq\.com/omn/\d{8}/\d{8}\.html",
        r"https?://new\.qq\.com/zt/template/\w+/\w+\.html",
        r"https?://news\.qq\.com/a/\d{8}/\d+\.htm",
        r"https?://new\.qq\.com/ch/[^\"'\s<>]+",
    ]
    for p in patterns:
        for m in re.finditer(p, channel_html):
            url = m.group(0).split("?")[0]
            if url not in seen:
                seen.add(url)
                urls.append(url)
    return urls


def _normalize_cms_id(raw: str) -> Optional[str]:
    """稿件 id 统一大写后再校验（链接里偶见小写）。"""
    s = (raw or "").strip().upper()
    return s if _ARTICLE_ID_RE.fullmatch(s) else None


def _rain_cms_id_from_url(url: str) -> Optional[str]:
    u = url.split("?")[0]
    for rx in _RAIN_ARTICLE_URL_RES:
        m = rx.search(u)
        if m:
            return _normalize_cms_id(m.group(1))
    return None


def _extract_cms_ids_embedded_in_html(html: str) -> List[str]:
    """
    从频道页 HTML 内联 JSON / script 中抽取稿件 id（页面未必输出完整 http 链接）。
    仅保留符合 _ARTICLE_ID_RE 的片段并去重保序。
    """
    if not html:
        return []
    seen: set[str] = set()
    out: List[str] = []

    def _take(s: str) -> None:
        nid = _normalize_cms_id(s)
        if not nid or nid in seen:
            return
        seen.add(nid)
        out.append(nid)

    # 常见：纯 id 串出现在 JSON 字段附近（长度不固定，从长到短尝试 fullmatch）
    for m in re.finditer(r"20\d{6}[A-Za-z][A-Za-z0-9]{4,40}", html):
        chunk = m.group(0).upper()
        for end in range(len(chunk), 11, -1):
            sub = chunk[:end]
            if _normalize_cms_id(sub):
                _take(sub)
                break

    for m in _RAIN_ESCAPED_PATH.finditer(html):
        nid = _normalize_cms_id(m.group(1))
        if nid:
            _take(nid)

    return out


def _merge_channel_article_ids(html: str, *, max_ids: int) -> List[Dict[str, str]]:
    """先 URL 正则，再补内联 id，去重保序。"""
    seen: set[str] = set()
    rows: List[Dict[str, str]] = []
    cap = max(1, max_ids)

    for u in _extract_article_urls_from_channel_html(html):
        if len(rows) >= cap:
            break
        nid = _rain_cms_id_from_url(u.split("?")[0])
        if nid and nid not in seen:
            seen.add(nid)
            rows.append({"id": nid, "title": ""})

    for nid in _extract_cms_ids_embedded_in_html(html):
        if len(rows) >= cap:
            break
        if nid not in seen:
            seen.add(nid)
            rows.append({"id": nid, "title": ""})

    return rows


def _document_headers(referer: str) -> Dict[str, str]:
    h = dict(_headers(referer=referer))
    h.pop("Origin", None)
    h["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    h["Sec-Fetch-Site"] = "none"
    h["Sec-Fetch-Mode"] = "navigate"
    h["Sec-Fetch-Dest"] = "document"
    return h


def _fetch_channel_html_requests(session: requests.Session, channel_url: str) -> str:
    r = session.get(channel_url, headers=_document_headers(channel_url), timeout=25)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def _playwright_launch_chromium(p: Any) -> Any:
    """优先 Playwright 自带 Chromium；未下载时尝试 Windows Edge / 本机 Chrome 通道。"""
    attempts: List[Dict[str, Any]] = [
        {"headless": True},
        {"headless": True, "channel": "msedge"},
        {"headless": True, "channel": "chrome"},
    ]
    last: Optional[Exception] = None
    for kw in attempts:
        try:
            browser = p.chromium.launch(**kw)
            ch = kw.get("channel") or "bundled"
            logger.info("[腾讯] Playwright 使用浏览器通道：%s", ch)
            return browser
        except Exception as e:
            last = e
            continue
    raise last if last else RuntimeError("Playwright 无法启动浏览器")


def _playwright_collect_rain_hrefs(page: Any) -> List[str]:
    """DOM 锚点 + 任意 href 属性 + 整页/同源 iframe innerHTML 正则（要闻等页常无裸 a[href]）。"""
    try:
        raw = page.evaluate(
            """() => {
                const out = new Set();
                const base = location.origin || 'https://news.qq.com';
                function addFromHref(raw) {
                    if (!raw || raw === '#' || raw.startsWith('javascript:')) return;
                    try {
                        const h = new URL(raw, base).href.split('#')[0].split('?')[0];
                        if (h.includes('/rain/a/')) out.add(h);
                    } catch (e) { /* ignore */ }
                }
                for (const el of document.querySelectorAll('a[href], area[href]')) {
                    addFromHref((el.getAttribute('href') || '').trim());
                }
                for (const el of document.querySelectorAll('[href*="rain"]')) {
                    const raw = el.getAttribute && el.getAttribute('href');
                    if (raw) addFromHref(String(raw).trim());
                }
                function scanHtml(html) {
                    if (!html) return;
                    const re = /https?:\\/\\/(?:new|news)\\.qq\\.com\\/rain\\/a\\/[A-Za-z0-9]+/gi;
                    let m;
                    while ((m = re.exec(html))) out.add(m[0].split('?')[0]);
                }
                scanHtml(document.documentElement ? document.documentElement.innerHTML : '');
                for (const f of document.querySelectorAll('iframe')) {
                    try {
                        const doc = f.contentDocument;
                        if (doc && doc.documentElement) scanHtml(doc.documentElement.innerHTML);
                    } catch (e) { /* cross-origin */ }
                }
                return [...out];
            }"""
        )
    except Exception as e:
        logger.debug("[腾讯] Playwright 收集 rain 链接失败：%s", e)
        return []
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw if isinstance(x, str) and "/rain/a/" in x]


def _rain_hrefs_from_raw_text(body: str) -> List[str]:
    """从任意文本（含 JSON 字符串、jsonp）里抽出 rain 绝对 URL。"""
    if not body or len(body) > 4_000_000:
        return []
    out: List[str] = []
    seen: set[str] = set()
    for m in re.finditer(r"https?://(?:new|news)\.qq\.com/rain/a/[A-Za-z0-9]+", body, re.I):
        u = m.group(0).split("?")[0]
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _inject_synthetic_rain_anchors(html: str, hrefs: List[str]) -> str:
    """把 DOM 收集到的 href 注入 HTML，供既有正则/合并逻辑解析。"""
    if not hrefs:
        return html
    seen: set[str] = set()
    parts: List[str] = []
    for h in hrefs:
        h = h.strip()
        if not h or h in seen:
            continue
        seen.add(h)
        esc = h.replace("&", "&amp;").replace('"', "&quot;")
        parts.append(f'<a href="{esc}"></a>')
    if not parts:
        return html
    return html + "\n<!-- tencent-synthetic-rain -->\n" + "\n".join(parts)


def _fetch_channel_html_playwright(channel_url: str) -> str:
    from playwright.sync_api import sync_playwright

    ua = _headers()["User-Agent"]
    # 要闻等页列表在 XHR/JSON 里，DOM 常无 <a href="/rain/a/">；监听响应与页面脚本里 SES/wx 无关
    net_hrefs: set[str] = set()

    def _on_response(response: Any) -> None:
        try:
            if response.status != 200:
                return
            u = response.url or ""
            if not any(
                k in u
                for k in (
                    "match.qq.com",
                    "pacaio",
                    "inews.qq.com",
                    "i.news.qq.com",
                    "view.inews.qq.com",
                    "/xw/",
                    "getSimpleNews",
                )
            ):
                return
            body = response.text()
            if len(body) > 3_000_000:
                return
            data: Any = None
            try:
                data = json.loads(body)
            except (json.JSONDecodeError, TypeError, ValueError):
                data = None
            if isinstance(data, (dict, list)):
                batch: List[Dict[str, str]] = []
                _walk_collect_list_items(data, batch)
                for row in batch:
                    nid = row.get("id") or ""
                    if isinstance(nid, str) and _ARTICLE_ID_RE.match(nid):
                        net_hrefs.add(f"https://news.qq.com/rain/a/{nid}")
            for h in _rain_hrefs_from_raw_text(body):
                net_hrefs.add(h)
        except Exception as e:
            logger.debug("[腾讯] Playwright response 解析跳过：%s", e)

    with sync_playwright() as p:
        browser = _playwright_launch_chromium(p)
        try:
            context = browser.new_context(user_agent=ua, locale="zh-CN")
            page = context.new_page()
            page.on("response", _on_response)
            page.goto(channel_url, wait_until="domcontentloaded", timeout=45000)
            try:
                page.wait_for_load_state("networkidle", timeout=25000)
            except Exception:
                pass
            page.wait_for_timeout(_TENCENT_PLAYWRIGHT_WAIT_MS)
            for _ in range(4):
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(1200)
            for _ in range(_TENCENT_PLAYWRIGHT_LOAD_MORE_ROUNDS):
                btn = page.locator("text=加载更多").first
                try:
                    if btn.is_visible(timeout=1500):
                        btn.click(timeout=2500)
                        page.wait_for_timeout(1800)
                        page.mouse.wheel(0, 2600)
                        page.wait_for_timeout(900)
                    else:
                        break
                except Exception:
                    break
            hrefs = _playwright_collect_rain_hrefs(page)
            # 列表常为异步挂载：rain 过少时再等、再滚、再采 1～2 轮
            for retry in range(2):
                if len(hrefs) >= 12:
                    break
                logger.info(
                    "[腾讯] Playwright rain 链接仅 %d 条，第 %d 次补等待与滚动",
                    len(hrefs),
                    retry + 1,
                )
                page.wait_for_timeout(2800 + retry * 1200)
                for _ in range(3):
                    page.mouse.wheel(0, 2800)
                    page.wait_for_timeout(700)
                more = _playwright_collect_rain_hrefs(page)
                seen = set(hrefs)
                for h in more:
                    if h not in seen:
                        seen.add(h)
                        hrefs.append(h)
            seen = set(hrefs)
            for h in net_hrefs:
                if h not in seen:
                    seen.add(h)
                    hrefs.append(h)
            if net_hrefs:
                logger.info("[腾讯] Playwright 网络响应补充 rain 链接 %d 条", len(net_hrefs))
            if hrefs:
                logger.info("[腾讯] Playwright 合并 rain 链接共 %d 条（DOM+网络）", len(hrefs))
            html = _inject_synthetic_rain_anchors(page.content(), hrefs)
            context.close()
        finally:
            browser.close()
    return html


def _get_channel_html_list_fallback(
    session: requests.Session,
    channel_url: str,
    *,
    min_ids_before_playwright: int,
) -> str:
    text = _fetch_channel_html_requests(session, channel_url)
    merged = _merge_channel_article_ids(text, max_ids=max(80, min_ids_before_playwright * 4))
    n_links = len(_extract_article_urls_from_channel_html(text))
    n_merged = len(merged)
    # 已从静态 HTML 解析到足够稿件 id 时，无需 Playwright（避免未 install chromium 时整段失败）
    if n_merged >= min_ids_before_playwright or n_links >= _TENCENT_CHANNEL_MIN_URLS_FOR_REQUESTS:
        logger.info(
            "[腾讯] 频道页静态解析：链接形态 %d 条，可用稿件 id %d 条（阈值 playwright=%d）",
            n_links,
            n_merged,
            min_ids_before_playwright,
        )
        return text
    if os.getenv("TENCENT_USE_PLAYWRIGHT", "1").strip().lower() in ("0", "false", "no"):
        logger.warning("[腾讯] 已设置 TENCENT_USE_PLAYWRIGHT=0，跳过浏览器渲染")
        return text
    try:
        rendered = _fetch_channel_html_playwright(channel_url)
        _delay(0.5, 0.25)
        return rendered
    except ImportError:
        logger.warning(
            "[腾讯] 栏目页候选较少且未安装 playwright：可 pip install playwright 后执行 playwright install chromium"
        )
        return text
    except Exception as e:
        logger.warning("[腾讯] 浏览器渲染栏目页失败，使用 requests 首屏 HTML：%s", e)
        return text


def _try_inews_pc_hot_ranking_list(
    session: requests.Session,
    *,
    referer: str,
    max_items: int,
) -> List[Dict[str, str]]:
    """
    与要闻 PC 页一致的 i.news 榜单接口（rank_id=hot）；返回 id+title。
    不依赖 Playwright 拦截 XHR，避免要闻页 iframe/时序导致 net_hrefs 为空。
    """
    ps = str(max(24, min(max_items * 4, 80)))
    params = {
        "ids_hash": "",
        "offset": "0",
        "page_size": ps,
        "appver": "15.5_qqnews_7.1.60",
        "rank_id": "hot",
    }
    try:
        r = session.get(
            INEWS_PC_HOT_RANK_URL,
            params=params,
            headers=_headers(referer=referer),
            timeout=35,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.debug("[腾讯] i.news pc_hot_ranking_list：%s", e)
        return []
    if not isinstance(data, dict) or data.get("ret") not in (0, None):
        return []
    found: List[Dict[str, str]] = []
    _walk_collect_list_items(data, found)
    out = _dedupe_preserve_order(found)
    if out:
        logger.info("[腾讯] i.news pc_hot_ranking_list 得到 %d 条候选", len(out))
    return out[: max(1, max_items)]


def _try_pacaio_article_list(
    session: requests.Session,
    channel_key: str,
    *,
    max_items: int,
) -> List[Dict[str, str]]:
    """
    频道页+Playwright 仍无可用 id 时尝试 pacaio 列表（要闻等栏目常见）。
    环境变量 TENCENT_PACAI_FALLBACK=0 可关闭。
    """
    if os.getenv("TENCENT_PACAI_FALLBACK", "1").strip().lower() in ("0", "false", "no"):
        return []
    if channel_key not in QQ_NEWS_CHANNELS:
        return []
    _, chlid = QQ_NEWS_CHANNELS[channel_key]
    referer = QQ_CHANNEL_WARM_URL.get(channel_key, "https://news.qq.com/ch/tech/")
    try:
        session.get(referer, headers=_document_headers(referer), timeout=22)
        _delay(0.35, 0.12)
    except Exception as e:
        logger.debug("[腾讯] pacaio 前频道预热忽略：%s", e)
    ps = str(max(12, min(max_items * 5, 40)))
    params = {
        "ext": chlid,
        "channel": chlid,
        "needPic": "0",
        "needNewArticle": "1",
        "page": "0",
        "pagesize": ps,
    }
    max_attempts = max(3, min(int(os.getenv("TENCENT_PACAI_MAX_ATTEMPTS", "6") or "6"), 10))
    for attempt in range(max_attempts):
        try:
            r = session.get(
                PACAI_LIST_URL,
                params=params,
                headers=_headers(referer=referer),
                timeout=45,
            )
            if r.status_code in (429, 500, 502, 503, 504):
                wait = min(25.0, (2**attempt) * 1.2 + random.uniform(0, 1.2))
                logger.warning(
                    "[腾讯] pacaio 备用列表 HTTP %s，%.1fs 后重试 (%d/%d)",
                    r.status_code,
                    wait,
                    attempt + 1,
                    max_attempts,
                )
                time.sleep(wait)
                continue
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            logger.debug("[腾讯] pacaio 备用尝试 %d/%d：%s", attempt + 1, max_attempts, e)
            time.sleep(min(12.0, 1.5 * (attempt + 1) + random.uniform(0, 0.5)))
            continue
        found: List[Dict[str, str]] = []
        _walk_collect_list_items(data, found)
        out = _dedupe_preserve_order(found)
        if out:
            logger.info("[腾讯] pacaio 备用列表得到 %d 条候选", len(out))
            return out[: max(1, max_items)]
    return []


def _fetch_channel_page_article_list(
    session: requests.Session,
    channel_key: str,
    *,
    max_urls: int,
) -> List[Dict[str, str]]:
    """频道页（requests/Playwright）+ 正则；全站首页预热与各频道逻辑一致；仍为空时 pacaio。"""
    try_urls = _channel_try_urls(channel_key)
    if not try_urls:
        return []

    _session_prefetch_news_home(session)

    min_pw = max(5, min(max_urls, 24))
    filtered: List[Dict[str, str]] = []

    # 要闻：列表在 i.news 榜单 JSON 中，频道页常无 rain 锚点；优先直连接口，省 Playwright 且不受 pacaio 503 影响
    if channel_key == "politics":
        ref = QQ_CHANNEL_WARM_URL.get("politics", "https://news.qq.com/ch/yaowen/")
        hot_rows = _try_inews_pc_hot_ranking_list(session, referer=ref, max_items=max_urls)
        for row in hot_rows:
            url = f"https://news.qq.com/rain/a/{row['id']}"
            if not _robots_allows(url):
                continue
            filtered.append(row)
            if len(filtered) >= max_urls:
                break
        if filtered:
            logger.info(
                "[腾讯] 频道 politics 经 i.news 榜单解析到稿件 id %d 条",
                len(filtered),
            )
            return filtered[: max(1, max_urls)]

    for channel_url in try_urls:
        if not _robots_allows(channel_url):
            logger.warning("[腾讯] robots 不允许抓取栏目：%s", channel_url)
            continue
        logger.info("[腾讯] 频道 %s 列表页尝试：%s", channel_key, channel_url)
        html = _get_channel_html_list_fallback(session, channel_url, min_ids_before_playwright=min_pw)
        out = _merge_channel_article_ids(html, max_ids=max(1, max_urls))
        batch: List[Dict[str, str]] = []
        for row in out:
            url = f"https://news.qq.com/rain/a/{row['id']}"
            if not _robots_allows(url):
                continue
            batch.append(row)
        if batch:
            filtered = batch
            logger.info(
                "[腾讯] 频道 %s 在 %s 解析到稿件 id %d 条",
                channel_key,
                channel_url,
                len(filtered),
            )
            break

    if not filtered:
        pac = _try_pacaio_article_list(session, channel_key, max_items=max_urls)
        for row in pac:
            url = f"https://news.qq.com/rain/a/{row['id']}"
            if not _robots_allows(url):
                continue
            filtered.append(row)
            if len(filtered) >= max_urls:
                break
    return filtered[: max(1, max_urls)]


def _strip_tencent_boilerplate(text: str) -> str:
    if not text:
        return text
    t = text
    t = re.sub(r"本文来自腾讯新闻客户端[^\n\r]*", "", t)
    t = re.sub(r"免责声明[^\n\r]*", "", t)
    return normalize_display_text(t.strip(), multiline=True)


def fetch_article_by_id(session: requests.Session, news_id: str, *, channel_key: str) -> Optional[Dict[str, Any]]:
    params = {"id": news_id, "refer": "pc"}
    r = session.get(
        SIMPLE_NEWS_URL,
        params=params,
        headers=_headers(referer=QQ_CHANNEL_WARM_URL.get(channel_key, "https://news.qq.com/ch/tech/")),
        timeout=40,
    )
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        return None
    ret = data.get("ret")
    if ret is not None and ret != 0:
        logger.debug("[腾讯] getSimpleNews ret=%s id=%s", ret, news_id)
        return None
    title = normalize_title(str(data.get("title") or ""))
    abstract = normalize_display_text(str(data.get("abstract") or ""), multiline=False)
    src = str(data.get("source") or "腾讯新闻")
    pub = str(data.get("time") or "")

    html_body = ""
    c = data.get("content")
    if isinstance(c, dict):
        html_body = str(c.get("text") or "")
    elif isinstance(c, str):
        html_body = c
    content = normalize_from_html_fragment(html_body) if html_body else ""
    if not content.strip() and abstract:
        content = abstract
    content = _strip_tencent_boilerplate(content)

    img = str(data.get("shareImg") or "")
    if not img and isinstance(data.get("attribute"), dict):
        # 首图
        for v in data["attribute"].values():
            if isinstance(v, dict) and v.get("origUrl"):
                img = str(v.get("origUrl") or "")
                break

    if not content.strip():
        return None

    return {
        "title": title or normalize_title(news_id),
        "url": f"https://news.qq.com/rain/a/{news_id}",
        "content": content,
        "description": abstract or (content[:400] if content else ""),
        "published_at": pub,
        "source": src,
        "author": "",
        "image_url": img,
        "source_type": "tencent_news_scrape",
    }


def scrape_tencent_channel(
    channel_key: str,
    *,
    limit: int = 10,
    list_delay_sec: Optional[float] = None,
    article_delay_sec: Optional[float] = None,
    article_jitter_sec: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    按频道 key（politics/tech/kepu/sports）抓取腾讯新闻。
    环境变量：TENCENT_NEWS_LIST_DELAY_SEC、TENCENT_NEWS_ARTICLE_DELAY_SEC、TENCENT_NEWS_JITTER_SEC
    """
    if not PERSONAL_USE_ONLY:
        logger.warning(
            "[腾讯] PERSONAL_USE_ONLY=False：请自行确保符合法律法规、腾讯服务条款及 robots，"
            "禁止未授权的大规模抓取或商用分发。"
        )

    key = (channel_key or "tech").strip().lower()
    if key not in QQ_NEWS_CHANNELS:
        raise ValueError(f"未知腾讯频道：{channel_key}，可选：{', '.join(QQ_NEWS_CHANNELS)}")

    if list_delay_sec is None:
        list_delay_sec = float(os.getenv("TENCENT_NEWS_LIST_DELAY_SEC", "0.6") or "0.6")
    if article_delay_sec is None:
        article_delay_sec = float(os.getenv("TENCENT_NEWS_ARTICLE_DELAY_SEC", "1.0") or "1.0")
    if article_jitter_sec is None:
        article_jitter_sec = float(os.getenv("TENCENT_NEWS_JITTER_SEC", "0.35") or "0.35")

    limit = max(1, min(int(limit), 10))
    scrape_t0 = time.perf_counter()

    session = _make_session()
    logger.info("[腾讯] 列表来源=频道页（requests + 可选 Playwright + 正则）")
    raw_list = _fetch_channel_page_article_list(
        session,
        key,
        max_urls=max(limit * 6, 80),
    )
    if not raw_list:
        raise RuntimeError(
            "腾讯新闻列表：未解析到有效稿件 ID。要闻依赖 i.news 榜单或频道页渲染；"
            "其它频道可安装 Playwright 并执行 playwright install chromium（或改用本机 Edge/Chrome 通道）。"
            "若 pacaio 连续返回 503，为腾讯侧限流，可稍后重试或暂时换频道。"
        )
    _delay(list_delay_sec, article_jitter_sec)

    articles: List[Dict[str, Any]] = []
    skipped = 0
    for item in raw_list:
        if len(articles) >= limit:
            break
        nid = item.get("id") or ""
        if not nid:
            continue
        try:
            art = fetch_article_by_id(session, nid, channel_key=key)
            _delay(article_delay_sec, article_jitter_sec)
        except Exception as e:
            logger.warning("[腾讯] 正文失败 id=%s: %s", nid, e)
            skipped += 1
            _delay(article_delay_sec * 0.5, article_jitter_sec)
            continue
        if not art:
            skipped += 1
            continue
        articles.append(art)
        logger.info(
            "[腾讯] 第 %d 篇 OK id=%s title=%r",
            len(articles),
            nid,
            (art.get("title") or "")[:50],
        )

    logger.info(
        "[腾讯] 结束 有效 %d 跳过/失败 %d 耗时 %.2fs",
        len(articles),
        skipped,
        time.perf_counter() - scrape_t0,
    )
    return articles
