
import httpx
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

async def test_google():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    query = "latest news about AI"
    google_url = f"https://www.google.com/search?q={quote_plus(query)}&hl=en"
    print(f"Testing Google search: {google_url}")
    
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        resp = await client.get(google_url)
        print(f"Status code: {resp.status_code}")
        
        with open("google_debug.html", "w") as f:
            f.write(resp.text)
        print("Saved google_debug.html")
        
        soup = BeautifulSoup(resp.text, "lxml")
        results = []
        for g in soup.select("div.g, div.tF2Cxc, div.MjjYud"):
            link = g.select_one("a[href]")
            title = g.select_one("h3")
            if link and title:
                results.append(title.get_text())
        
        print(f"Found {len(results)} results")
        for r in results[:5]:
            print(f"- {r}")

if __name__ == "__main__":
    asyncio.run(test_google())
