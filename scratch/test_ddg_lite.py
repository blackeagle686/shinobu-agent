
import httpx
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

async def test_ddg_lite():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    query = "latest news about AI"
    # DuckDuckGo Lite URL
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    print(f"Testing DDG Lite: {url}")
    
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        resp = await client.get(url)
        print(f"Status code: {resp.status_code}")
        
        with open("ddg_lite_debug.html", "w") as f:
            f.write(resp.text)
        print("Saved ddg_lite_debug.html")
        
        soup = BeautifulSoup(resp.text, "lxml")
        results = []
        # DDG Lite selectors are different
        for link in soup.select(".result__a"):
            title = link.get_text()
            href = link.get("href")
            results.append((title, href))
        
        print(f"Found {len(results)} results")
        for title, href in results[:5]:
            print(f"- {title} ({href})")

if __name__ == "__main__":
    asyncio.run(test_ddg_lite())
