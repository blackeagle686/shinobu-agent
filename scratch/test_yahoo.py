
import httpx
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

async def test_yahoo():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    query = "latest news about AI"
    url = f"https://search.yahoo.com/search?p={quote_plus(query)}"
    print(f"Testing Yahoo search: {url}")
    
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        resp = await client.get(url)
        print(f"Status code: {resp.status_code}")
        
        soup = BeautifulSoup(resp.text, "lxml")
        results = []
        for g in soup.select(".algo-sr, .dd.algo"):
            link = g.select_one("a")
            title = g.select_one("h3")
            snippet = g.select_one(".compText, .st")
            if link and title:
                results.append({
                    "title": title.get_text(strip=True),
                    "url": link.get("href"),
                    "snippet": snippet.get_text(strip=True) if snippet else ""
                })
        
        print(f"Found {len(results)} results")
        for r in results[:5]:
            print(f"- {r['title']} ({r['url']})")

if __name__ == "__main__":
    asyncio.run(test_yahoo())
