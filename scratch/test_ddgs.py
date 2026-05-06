from ddgs import DDGS
import json

with DDGS() as ddgs:
    results = [r for r in ddgs.text("python programming", max_results=5)]
    print(json.dumps(results, indent=2))
