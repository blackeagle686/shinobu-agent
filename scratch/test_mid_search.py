
import asyncio
import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from Shinobu.shinobu.services.webbrowser import WebBrowserService

async def test_mid_search():
    browser = WebBrowserService()
    query = "latest news about AI"
    print(f"Testing mid_search for: {query}")
    result = await browser.mid_search(query)
    print(f"Success: {result.get('success')}")
    print(f"Engine used: {result.get('engine')}")
    print(f"Result count: {result.get('result_count')}")
    if result.get('results'):
        for r in result['results'][:3]:
            print(f"- {r['title']} ({r['url']})")
    else:
        print("No results found.")
    
    if result.get('error'):
        print(f"Error: {result['error']}")

if __name__ == "__main__":
    asyncio.run(test_mid_search())
