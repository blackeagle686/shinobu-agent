
from ddgs import DDGS
import json

def test_ddgs():
    try:
        print("Testing DDGS library...")
        with DDGS() as ddgs:
            results = list(ddgs.text("latest news about AI", max_results=5))
            print(f"Found {len(results)} results")
            for r in results:
                print(f"- {r['title']} ({r['href']})")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_ddgs()
