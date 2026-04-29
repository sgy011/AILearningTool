"""
百度图片抓取（Playwright 浏览器自动化）。

注意：站点条款与反爬限制需调用方自行承担；本模块尽量做到节流与上限保护。
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import List, Set
from urllib.parse import quote

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScrapedImage:
    url: str
    source: str  # e.g. "baidu"


def _sleep_jitter(base_ms: int, *, jitter_ms: int = 250) -> None:
    base = max(0, int(base_ms))
    j = max(0, int(jitter_ms))
    t = (base + random.randint(0, j)) / 1000.0
    time.sleep(t)


def scrape_baidu_image_urls(
    query: str,
    *,
    count: int,
    max_links: int = 800,
    scroll_rounds: int = 50,
    delay_ms: int = 150,
    timeout_sec: int = 30,
    headless: bool = True,
    goto_retries: int = 3,
) -> List[ScrapedImage]:
    """
    返回尽量多的图片 URL（未下载）。
    
    性能优化：
    - 降低默认延迟 (350ms -> 150ms)
    - 减少默认滚动轮数 (80 -> 50)
    - 缩短超时时间 (45s -> 30s)
    """
    q = (query or "").strip()
    if not q:
        return []
    want = max(1, int(count))
    max_links = max(want, int(max_links))

    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "未安装 Playwright：请执行 pip install playwright && playwright install chromium"
        ) from e

    urls: List[ScrapedImage] = []
    seen: Set[str] = set()

    search_url = (
        "https://image.baidu.com/search/index?"
        "tn=baiduimage&ipn=r&word=" + quote(q, safe="")
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = ctx.new_page()
        page.set_default_timeout(timeout_sec * 1000)
        try:
            # 带重试的页面加载
            last_err = None
            for attempt in range(1, goto_retries + 1):
                try:
                    page.goto(search_url, wait_until="domcontentloaded")
                    break
                except Exception as exc:
                    last_err = exc
                    if attempt < goto_retries:
                        wait_s = attempt * 2
                        logger.warning(
                            "baidu goto attempt %d/%d failed: %s, retrying in %ds",
                            attempt, goto_retries, exc, wait_s,
                        )
                        time.sleep(wait_s)
                    else:
                        logger.error(
                            "baidu goto all %d attempts failed for query=%r",
                            goto_retries, q,
                        )
                        raise last_err
            _sleep_jitter(delay_ms)

            def harvest() -> None:
                nonlocal urls
                # 从 DOM 抽取可能的图片链接（data-objurl / data-imgurl / data-src / src）
                candidates = page.evaluate(
                    """() => {
                      const out = [];
                      const imgs = Array.from(document.querySelectorAll('img'));
                      for (const im of imgs) {
                        const u = im.getAttribute('data-objurl')
                          || im.getAttribute('data-imgurl')
                          || im.getAttribute('data-src')
                          || im.getAttribute('src')
                          || '';
                        if (!u) continue;
                        out.push(u);
                      }
                      const as = Array.from(document.querySelectorAll('a'));
                      for (const a of as) {
                        const u = a.getAttribute('href') || '';
                        if (u && (u.startsWith('http://') || u.startsWith('https://'))) out.push(u);
                      }
                      return out;
                    }"""
                )
                if not isinstance(candidates, list):
                    return
                for u in candidates:
                    if not isinstance(u, str):
                        continue
                    t = u.strip()
                    if not t or t.startswith("data:"):
                        continue
                    if not (t.startswith("http://") or t.startswith("https://")):
                        continue
                    if t in seen:
                        continue
                    seen.add(t)
                    urls.append(ScrapedImage(url=t, source="baidu"))

            harvest()
            # 优化滚动策略：前半段快速滚动（大步长），后半段慢速滚动
            fast_rounds = int(scroll_rounds * 0.6)
            slow_rounds = scroll_rounds - fast_rounds
            
            for round_idx in range(int(scroll_rounds)):
                if len(urls) >= max_links or len(urls) >= want:
                    break
                # 动态调整滚动距离：前期快、后期慢
                if round_idx < fast_rounds:
                    scroll_dist = 3000  # 快速阶段
                    current_delay = max(80, delay_ms // 2)
                else:
                    scroll_dist = 1800  # 精细加载阶段
                    current_delay = delay_ms
                    
                page.mouse.wheel(0, scroll_dist)
                _sleep_jitter(current_delay)
                harvest()
        finally:
            try:
                page.close()
            except Exception:
                pass
            try:
                ctx.close()
            except Exception:
                pass
            browser.close()

    logger.info("baidu scrape query=%r got=%d", q, len(urls))
    return urls[:max_links]

