
import asyncio
import os
import sys
import json

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shinobu.services.webbrowser import WebBrowserService

async def main():
    service = WebBrowserService()
    query = "latest AI news"
    print(f"Testing deep_search for: {query}")
    
    try:
        # Deep search scrapes results and then individual pages
        result = await service.deep_search(query, max_pages=2)
        
        print("\n--- Result ---")
        print(f"Success: {result.get('success')}")
        print(f"Pages requested: {result.get('pages_requested')}")
        print(f"Pages scraped: {result.get('pages_scraped')}")
        
        if result.get('success') and 'pages' in result:
            for p in result['pages']:
                print(f"\n- Page: {p.get('title')}")
                print(f"  URL: {p.get('url')}")
                print(f"  Scrape Success: {p.get('scrape_success')}")
                if p.get('scrape_success'):
                    print(f"  Word Count: {p.get('word_count')}")
                    print(f"  Content Preview: {p.get('content')[:200]}...")
                else:
                    print(f"  Error: {p.get('error')}")
        else:
            print(f"Error: {result.get('error')}")
            
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        await service.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
