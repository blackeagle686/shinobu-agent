import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shinobu.services.webbrowser import WebBrowserService

async def test_search():
    service = WebBrowserService()
    print("🔍 Testing Mid Search (Result List)...")
    results = await service.mid_search("latest AI news 2026")
    
    if results.get("success"):
        print(f"✅ Found {len(results.get('results', []))} results via {results.get('engine')}")
        for r in results.get("results", []):
            print(f"  - {r['title']} ({r['url']})")
    else:
        print(f"❌ Search Failed: {results.get('error')}")

    print("\n🔍 Testing Deep Scrape (Single Page)...")
    if results.get("results"):
        first_url = results["results"][0]["url"]
        scrape = await service.scrape_page(first_url)
        if scrape.get("success"):
            print(f"✅ Scraped {scrape.get('title')}")
            print(f"   Word count: {scrape.get('word_count')}")
            print(f"   Preview: {scrape.get('body_text')[:200]}...")
        else:
            print(f"❌ Scrape Failed: {scrape.get('error')}")
    
    await service.shutdown()

if __name__ == "__main__":
    asyncio.run(test_search())
