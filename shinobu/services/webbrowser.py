"""
WebBrowserService — Shinobu's browser execution engine.

This is a PURE EXECUTION layer. No intelligence lives here.
Shinobu (via SearchLevelClassifier) decides WHAT to do;
this service decides HOW to do it.

Three tiers:
  🟢 Fast  — xdg-open (system browser, instant)
  🟡 Mid   — Playwright headless (controlled browsing)
  🔵 Deep  — httpx + BeautifulSoup (scraping + extraction)
"""

import os
import re
import json
import asyncio
import hashlib
import time
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urljoin, urlparse
from enum import Enum

logger = logging.getLogger("shinobu.services.webbrowser")


# ─────────────────────────────────────────────────────────────────────────────
# Search Level Enum
# ─────────────────────────────────────────────────────────────────────────────

class SearchLevel(Enum):
    FAST = "fast"    # Open browser, redirect — zero processing
    MID  = "mid"     # Headless browse, navigate, collect links
    DEEP = "deep"    # Scrape, extract, structure, prepare for LLM


# ─────────────────────────────────────────────────────────────────────────────
# Search Cache (Deep Search persistence with TTL)
# ─────────────────────────────────────────────────────────────────────────────

class SearchCache:
    """
    File-based cache for Deep Search results.
    Stores processed data (not raw HTML) with TTL expiration.
    """

    DEFAULT_TTL_HOURS = 24  # general knowledge
    NEWS_TTL_HOURS = 6      # trending / time-sensitive

    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = Path(cache_dir or os.path.expanduser("~/.shinobu_search_cache"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key(self, query: str) -> str:
        return hashlib.sha256(query.lower().strip().encode()).hexdigest()[:16]

    def _path(self, query: str) -> Path:
        return self.cache_dir / f"{self._key(query)}.json"

    def get(self, query: str, ttl_hours: Optional[int] = None) -> Optional[Dict]:
        """Retrieve cached result if it exists and hasn't expired."""
        path = self._path(query)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            ttl = ttl_hours or self.DEFAULT_TTL_HOURS
            age_hours = (time.time() - data.get("timestamp", 0)) / 3600
            if age_hours > ttl:
                path.unlink(missing_ok=True)
                return None
            logger.info(f"Cache hit for '{query}' (age: {age_hours:.1f}h)")
            return data
        except Exception:
            return None

    def put(self, query: str, results: Dict) -> None:
        """Store processed search results."""
        results["timestamp"] = time.time()
        results["query"] = query
        try:
            self._path(query).write_text(
                json.dumps(results, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"Cache write failed: {e}")

    def clear(self) -> int:
        """Remove all cached entries. Returns count of removed files."""
        count = 0
        for f in self.cache_dir.glob("*.json"):
            f.unlink(missing_ok=True)
            count += 1
        return count


# ─────────────────────────────────────────────────────────────────────────────
# URL & Known-Site Helpers
# ─────────────────────────────────────────────────────────────────────────────

# Direct-open sites: skip search, go straight to URL
KNOWN_SITES = {
    "youtube":    "https://www.youtube.com",
    "netflix":    "https://www.netflix.com",
    "github":     "https://github.com",
    "twitter":    "https://twitter.com",
    "x":          "https://x.com",
    "reddit":     "https://www.reddit.com",
    "google":     "https://www.google.com",
    "spotify":    "https://open.spotify.com",
    "wikipedia":  "https://www.wikipedia.org",
    "amazon":     "https://www.amazon.com",
    "facebook":   "https://www.facebook.com",
    "instagram":  "https://www.instagram.com",
    "linkedin":   "https://www.linkedin.com",
    "twitch":     "https://www.twitch.tv",
    "stackoverflow": "https://stackoverflow.com",
}

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def resolve_url(query: str) -> Optional[str]:
    """If query is a URL or a known site name, return the URL. Else None."""
    # Direct URL
    m = _URL_RE.search(query)
    if m:
        return m.group(0)
    # Known site name
    key = query.strip().lower().replace(" ", "")
    return KNOWN_SITES.get(key)


def duckduckgo_url(query: str, lite: bool = True) -> str:
    """Build a DuckDuckGo search URL."""
    if lite:
        return f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    return f"https://duckduckgo.com/?q={quote_plus(query)}"


def clean_ddg_url(url: str) -> str:
    """
    Extract the real target URL from a DuckDuckGo redirector link.
    Example: //duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com -> https://example.com
    """
    if not url:
        return ""
    
    # Handle protocol-relative URLs
    if url.startswith("//"):
        url = "https:" + url
        
    if "uddg=" in url:
        from urllib.parse import unquote, urlparse, parse_qs
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        uddg = params.get("uddg")
        if uddg:
            return unquote(uddg[0])
            
    return url


# ─────────────────────────────────────────────────────────────────────────────
# WebBrowserService
# ─────────────────────────────────────────────────────────────────────────────

class WebBrowserService:
    """
    Shinobu's browser execution engine.

    Design Rules:
      • No intelligence — only execution.
      • Shinobu (SearchLevelClassifier) controls everything.
      • Each method is a clean, testable unit of work.
    """

    # Browser Identity Pool
    _USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    ]

    @property
    def _HEADERS(self) -> Dict[str, str]:
        import random
        return {
            "User-Agent": random.choice(self._USER_AGENTS),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }

    _TIMEOUT = 20.0

    def __init__(self):
        self.cache = SearchCache()
        self._playwright_available: Optional[bool] = None
        self._browser = None
        self._playwright = None

    # ──────────────────────────────────────────────────────────────────────
    # 🟢 FAST SEARCH — System browser, instant, zero processing
    # ──────────────────────────────────────────────────────────────────────

    async def open_url(self, url: str) -> Dict[str, Any]:
        """Open a URL in the default system browser."""
        try:
            process = await asyncio.create_subprocess_shell(
                f"xdg-open '{url}'",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await process.wait()
            return {"success": True, "action": "open_url", "url": url}
        except Exception as e:
            return {"success": False, "action": "open_url", "error": str(e)}

    async def fast_search(self, query: str) -> Dict[str, Any]:
        """
        Fast Search: resolve to URL and open in system browser.
        If query is a known site → open directly.
        Otherwise → open DuckDuckGo search in browser.
        """
        url = resolve_url(query)
        if url:
            result = await self.open_url(url)
            result["resolved"] = True
            return result

        # Open search in browser
        search_url = duckduckgo_url(query)
        result = await self.open_url(search_url)
        result["resolved"] = False
        result["search_url"] = search_url
        return result

    # ──────────────────────────────────────────────────────────────────────
    # 🟡 MID SEARCH — Headless browsing, controlled navigation
    # ──────────────────────────────────────────────────────────────────────

    async def _check_playwright(self) -> bool:
        """Check if Playwright is available (cached result)."""
        if self._playwright_available is not None:
            return self._playwright_available
        try:
            import playwright  # noqa: F401
            self._playwright_available = True
        except ImportError:
            self._playwright_available = False
            logger.warning(
                "Playwright not installed — Mid Search will use httpx fallback. "
                "Install with: pip install playwright && playwright install chromium"
            )
        return self._playwright_available

    async def _get_browser(self):
        """Lazy-init Playwright browser (reused across calls)."""
        if self._browser is not None:
            return self._browser
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        return self._browser

    async def _close_browser(self):
        """Cleanup Playwright resources."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def mid_search(self, query: str) -> Dict[str, Any]:
        """
        Mid Search: search DuckDuckGo in headless browser, return structured results.
        Falls back to httpx if Playwright is unavailable.
        """
        if await self._check_playwright():
            return await self._mid_search_playwright(query)
        else:
            return await self._mid_search_httpx(query)

    async def _mid_search_playwright(self, query: str) -> Dict[str, Any]:
        """Mid Search via Playwright — full browser control."""
        try:
            browser = await self._get_browser()
            page = await browser.new_page()
            await page.set_extra_http_headers(self._HEADERS)

            # Navigate to DuckDuckGo
            await page.goto(duckduckgo_url(query), timeout=int(self._TIMEOUT * 1000))
            await page.wait_for_load_state("domcontentloaded")

            # Extract search results with resilient selectors
            results = await page.evaluate("""() => {
                const items = [];
                // Try multiple common result selectors
                const containers = document.querySelectorAll('.result, .links_main, article');
                
                containers.forEach((el, i) => {
                    if (items.length >= 10) return;
                    const titleEl = el.querySelector('.result__a, a.result__a, h2 a');
                    const snippetEl = el.querySelector('.result__snippet, .snippet, .result__body');
                    const urlEl = el.querySelector('.result__url, .url');
                    
                    const rawUrl = titleEl.href;
                    const imgEl = el.querySelector('.tile--img__img, .result__icon__img, img');
                    
                    if (rawUrl && !rawUrl.includes('duckduckgo.com/y.js')) {
                        items.push({
                            index: items.length + 1,
                            title: titleEl.textContent.trim(),
                            url: rawUrl,
                            image: imgEl ? imgEl.src : null,
                            snippet: snippetEl ? snippetEl.textContent.trim() : '',
                            display_url: urlEl ? urlEl.textContent.trim() : ''
                        });
                    }
                });
                return items;
            }""")

            # Step 2: Clean URLs and Deduplicate
            seen_urls = set()
            cleaned_results = []
            for r in results:
                real_url = clean_ddg_url(r["url"])
                if real_url not in seen_urls:
                    from urllib.parse import urlparse
                    domain = urlparse(real_url).netloc
                    r["url"] = real_url
                    r["favicon"] = f"https://www.google.com/s2/favicons?sz=64&domain_url={domain}"
                    cleaned_results.append(r)
                    seen_urls.add(real_url)

            await page.close()

            return {
                "success": True,
                "action": "mid_search",
                "engine": "playwright",
                "query": query,
                "result_count": len(cleaned_results),
                "results": cleaned_results,
            }
        except Exception as e:
            logger.error(f"Playwright mid search failed: {e}")
            # Fallback to httpx
            return await self._mid_search_httpx(query)

    async def _mid_search_httpx(self, query: str) -> Dict[str, Any]:
        """Mid Search fallback via httpx — no JS rendering."""
        import httpx
        from bs4 import BeautifulSoup

        try:
            async with httpx.AsyncClient(
                headers=self._HEADERS,
                timeout=self._TIMEOUT,
                follow_redirects=True,
            ) as client:
                resp = await client.get(duckduckgo_url(query))
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")
            results = []
            results_seen = set()

            # Extract with resilient selectors
            for i, result_div in enumerate(soup.select(".result, .links_main, article")):
                if len(results) >= 10:
                    break
                title_el = result_div.select_one(".result__a, a.result__a, h2 a")
                snippet_el = result_div.select_one(".result__snippet, .snippet, .result__body")
                url_el = result_div.select_one(".result__url, .url")

                if title_el and title_el.get("href"):
                    raw_url = title_el.get("href")
                    if "duckduckgo.com/y.js" in raw_url: continue
                    
                    real_url = clean_ddg_url(raw_url)
                    if real_url and real_url not in results_seen:
                        from urllib.parse import urlparse
                        domain = urlparse(real_url).netloc
                        
                        results.append({
                            "index": len(results) + 1,
                            "title": title_el.get_text(strip=True),
                            "url": real_url,
                            "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                            "display_url": url_el.get_text(strip=True) if url_el else "",
                            "favicon": f"https://www.google.com/s2/favicons?sz=64&domain_url={domain}",
                            "image": None # Lite mode doesn't have thumbnails
                        })
                        results_seen.add(real_url)

            return {
                "success": True,
                "action": "mid_search",
                "engine": "httpx",
                "query": query,
                "result_count": len(results),
                "results": results,
            }
        except Exception as e:
            return {"success": False, "action": "mid_search", "error": str(e)}

    async def navigate_to(self, url: str) -> Dict[str, Any]:
        """Navigate to a URL in headless browser, return page info."""
        if await self._check_playwright():
            return await self._navigate_playwright(url)
        else:
            return await self._navigate_httpx(url)

    async def _navigate_playwright(self, url: str) -> Dict[str, Any]:
        """Navigate via Playwright — full JS rendering."""
        try:
            browser = await self._get_browser()
            page = await browser.new_page()
            await page.set_extra_http_headers(self._HEADERS)
            await page.goto(url, timeout=int(self._TIMEOUT * 1000))
            await page.wait_for_load_state("domcontentloaded")

            title = await page.title()
            content = await page.content()

            # Extract visible text
            text = await page.evaluate("""() => {
                return document.body ? document.body.innerText.substring(0, 5000) : '';
            }""")

            await page.close()

            return {
                "success": True,
                "action": "navigate",
                "engine": "playwright",
                "url": url,
                "title": title,
                "text_preview": text[:2000],
                "content_length": len(content),
            }
        except Exception as e:
            return {"success": False, "action": "navigate", "error": str(e)}

    async def _navigate_httpx(self, url: str) -> Dict[str, Any]:
        """Navigate via httpx — static HTML only."""
        import httpx
        from bs4 import BeautifulSoup

        try:
            async with httpx.AsyncClient(
                headers=self._HEADERS,
                timeout=self._TIMEOUT,
                follow_redirects=True,
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")
            title = soup.title.string.strip() if soup.title and soup.title.string else ""
            text = soup.get_text(separator="\n", strip=True)[:2000]

            return {
                "success": True,
                "action": "navigate",
                "engine": "httpx",
                "url": url,
                "title": title,
                "text_preview": text,
                "content_length": len(resp.text),
            }
        except Exception as e:
            return {"success": False, "action": "navigate", "error": str(e)}

    async def get_page_links(self, url: str, max_links: int = 20) -> Dict[str, Any]:
        """Extract all links from a page."""
        import httpx
        from bs4 import BeautifulSoup

        try:
            async with httpx.AsyncClient(
                headers=self._HEADERS,
                timeout=self._TIMEOUT,
                follow_redirects=True,
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")
            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith(("http://", "https://")):
                    full_url = href
                elif href.startswith("/"):
                    full_url = urljoin(url, href)
                else:
                    continue
                text = a.get_text(strip=True)
                if text and len(text) > 2:
                    links.append({"text": text[:100], "url": full_url})
                if len(links) >= max_links:
                    break

            return {
                "success": True,
                "action": "get_links",
                "url": url,
                "link_count": len(links),
                "links": links,
            }
        except Exception as e:
            return {"success": False, "action": "get_links", "error": str(e)}

    # ──────────────────────────────────────────────────────────────────────
    # 🔵 DEEP SEARCH — Scrape, extract, structure
    # ──────────────────────────────────────────────────────────────────────

    async def scrape_page(self, url: str, use_playwright: bool = True) -> Dict[str, Any]:
        """
        Deep scrape a single page with high robustness.
        Uses Playwright (if available) for JS rendering and better bot evasion,
        falling back to httpx for static/fast cases or if Playwright fails.
        """
        if use_playwright and await self._check_playwright():
            result = await self._scrape_page_playwright(url)
            if result.get("success"):
                return result
            logger.warning(f"Playwright scrape failed for {url}, falling back to httpx: {result.get('error')}")

        return await self._scrape_page_httpx(url)

    async def _scrape_page_playwright(self, url: str) -> Dict[str, Any]:
        """Scrape via Playwright — handles JS and bypasses basic bot detection."""
        try:
            browser = await self._get_browser()
            # Create context with realistic dimensions and user agent
            context = await browser.new_context(
                user_agent=self._HEADERS["User-Agent"],
                viewport={"width": 1280, "height": 800},
                extra_http_headers={"Referer": "https://www.google.com/"}
            )
            page = await context.new_page()
            
            # Navigate with a generous timeout and wait condition
            response = await page.goto(url, timeout=int(self._TIMEOUT * 1500), wait_until="domcontentloaded")
            
            if not response or response.status >= 400:
                await context.close()
                return {"success": False, "error": f"HTTP {response.status if response else 'No Response'}"}

            # Wait a bit for JS to settle (optional but helpful for some sites)
            await asyncio.sleep(1.5)

            title = await page.title()
            content_html = await page.content()
            
            # Extract via BeautifulSoup from the rendered content
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content_html, "lxml")
            
            scraped_data = self._process_soup(soup, url)
            scraped_data["engine"] = "playwright"
            
            await context.close()
            return scraped_data
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _scrape_page_httpx(self, url: str) -> Dict[str, Any]:
        """Scrape via httpx — fast but fails on JS-heavy or bot-protected sites."""
        import httpx
        from bs4 import BeautifulSoup

        try:
            headers = self._HEADERS.copy()
            headers["Referer"] = "https://www.google.com/"
            
            async with httpx.AsyncClient(
                headers=headers,
                timeout=self._TIMEOUT,
                follow_redirects=True,
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")
            scraped_data = self._process_soup(soup, url)
            scraped_data["engine"] = "httpx"
            return scraped_data
        except Exception as e:
            return {"success": False, "url": url, "error": str(e)}

    def _process_soup(self, soup, url: str) -> Dict[str, Any]:
        """Common logic to extract and clean content from BeautifulSoup."""
        # Find potential main image (OG image or first high-quality img)
        og_image = soup.find("meta", attrs={"property": "og:image"}) or \
                   soup.find("meta", attrs={"name": "twitter:image"})
        main_image = og_image.get("content") if og_image else None
        
        if not main_image:
            first_img = soup.find("img", attrs={"src": re.compile(r"http")})
            if first_img:
                main_image = first_img.get("src")

        # Remove noise but KEEP img for potential inline rendering (though we summarize)
        for tag in soup(["script", "style", "nav", "footer", "header", 
                         "aside", "noscript", "iframe", "svg", "ad", "form"]):
            tag.decompose()

        # Title
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        
        # Meta description
        meta_desc = ""
        meta_tag = soup.find("meta", attrs={"name": "description"}) or \
                   soup.find("meta", attrs={"property": "og:description"})
        if meta_tag:
            meta_desc = meta_tag.get("content", "").strip()

        # Headings
        headings = []
        for level in range(1, 4):
            for h in soup.find_all(f"h{level}"):
                text = h.get_text(strip=True)
                if text and len(text) > 3:
                    headings.append({"level": level, "text": text[:200]})

        # Smart Content Extraction
        main_content = soup.find("article") or soup.find("main") or \
                       soup.find("div", class_=re.compile(r"content|article|post|body", re.I))
        target = main_content if main_content else soup.body
        
        paragraphs = []
        if target:
            for p in target.find_all(["p", "div", "li"]):
                text = p.get_text(strip=True)
                if len(text) > 60:
                    paragraphs.append(text)

        # Fallback: Body text
        body_text = soup.get_text(separator="\n", strip=True)
        body_text = re.sub(r"\n{3,}", "\n\n", body_text)

        return {
            "success": True,
            "url": url,
            "title": title,
            "meta_description": meta_desc,
            "main_image": main_image,
            "headings": headings[:30],
            "paragraphs": paragraphs[:25],
            "body_text": body_text[:10000],
            "word_count": len(body_text.split()),
        }

    async def deep_search(
        self,
        query: str,
        max_pages: int = 3,
        max_pages_extended: int = 5,
        extended: bool = False,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """
        Deep Search: search → collect top results → scrape each → return structured data.

        Args:
            query: search query
            max_pages: default number of results to scrape (3)
            max_pages_extended: extended mode limit (5)
            extended: whether to use extended mode
            use_cache: whether to check/update cache
        """
        limit = max_pages_extended if extended else max_pages

        # ── Check cache ──
        if use_cache:
            cached = self.cache.get(query)
            if cached:
                cached["from_cache"] = True
                return cached

        # ── Step 1: Get search results (via Mid Search engine) ──
        search_results = await self.mid_search(query)
        if not search_results.get("success"):
            return {
                "success": False,
                "action": "deep_search",
                "query": query,
                "error": search_results.get("error", "Search failed"),
            }

        results_list = search_results.get("results", [])[:limit]
        if not results_list:
            return {
                "success": False,
                "action": "deep_search",
                "query": query,
                "error": "No search results found",
            }

        # ── Step 2: Scrape each result page concurrently ──
        scrape_tasks = []
        for r in results_list:
            url = r.get("url", "")
            if url and url.startswith("http"):
                scrape_tasks.append(self.scrape_page(url))

        scraped = await asyncio.gather(*scrape_tasks, return_exceptions=True)

        # ── Step 3: Structure the results ──
        pages = []
        for i, (result, page_data) in enumerate(zip(results_list, scraped)):
            if isinstance(page_data, Exception):
                pages.append({
                    "index": i + 1,
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "snippet": result.get("snippet", ""),
                    "scrape_success": False,
                    "error": str(page_data),
                })
            elif not page_data.get("success"):
                pages.append({
                    "index": i + 1,
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "snippet": result.get("snippet", ""),
                    "scrape_success": False,
                    "error": page_data.get("error", "Unknown"),
                })
            else:
                pages.append({
                    "index": i + 1,
                    "title": page_data.get("title") or result.get("title", ""),
                    "url": result.get("url", ""),
                    "snippet": result.get("snippet", ""),
                    "scrape_success": True,
                    "meta_description": page_data.get("meta_description", ""),
                    "headings": page_data.get("headings", []),
                    "content": "\n\n".join(page_data.get("paragraphs", []))[:4000],
                    "word_count": page_data.get("word_count", 0),
                })

        deep_result = {
            "success": True,
            "action": "deep_search",
            "query": query,
            "pages_requested": limit,
            "pages_scraped": sum(1 for p in pages if p.get("scrape_success")),
            "pages": pages,
            "from_cache": False,
        }

        # ── Cache the result ──
        if use_cache:
            self.cache.put(query, deep_result)

        return deep_result

    # ──────────────────────────────────────────────────────────────────────
    # Cleanup
    # ──────────────────────────────────────────────────────────────────────

    async def shutdown(self):
        """Clean up all resources (call on agent shutdown)."""
        await self._close_browser()

    def __del__(self):
        """Best-effort cleanup."""
        if self._browser or self._playwright:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.shutdown())
            except RuntimeError:
                pass
