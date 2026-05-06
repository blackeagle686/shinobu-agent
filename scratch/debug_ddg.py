
import asyncio
import sys
import os
from playwright.async_api import async_playwright

async def debug_ddg():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        query = "latest news about AI"
        url = f"https://duckduckgo.com/?q={query}"
        print(f"Navigating to {url}")
        await page.goto(url)
        await asyncio.sleep(5) # Wait for results
        
        content = await page.content()
        with open("ddg_debug.html", "w") as f:
            f.write(content)
        print("Saved ddg_debug.html")
        
        containers = await page.query_selector_all('[data-testid="result"], article, .result')
        print(f"Found {len(containers)} containers")
        
        for i, el in enumerate(containers[:3]):
            title_el = await el.query_selector('[data-testid="result-title-a"], h2 a, .result__a')
            if title_el:
                title = await title_el.inner_text()
                href = await title_el.get_attribute("href")
                print(f"Result {i+1}: {title} ({href})")
            else:
                print(f"Result {i+1}: Title element not found")
                # Print outer HTML of container to see what's inside
                html = await el.evaluate("el => el.outerHTML")
                print(f"Container HTML: {html[:200]}...")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_ddg())
