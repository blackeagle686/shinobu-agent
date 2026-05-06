
import asyncio
import os
import sys
import json

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shinobu.services.webbrowser import WebBrowserService

async def main():
    service = WebBrowserService()
    query = "latest news about AI"
    print(f"Testing mid_search for: {query}")
    
    try:
        # Try mid_search which uses Playwright first then fallback to HTTPX
        result = await service.mid_search(query)
        
        print("\n--- Result ---")
        print(f"Success: {result.get('success')}")
        print(f"Engine: {result.get('engine')}")
        print(f"Result Count: {result.get('result_count', 0)}")
        
        if result.get('success') and 'results' in result:
            for r in result['results'][:5]:
                print(f"- {r['title']} ({r['url']})")
        else:
            print(f"Error: {result.get('error')}")
            
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        await service.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
