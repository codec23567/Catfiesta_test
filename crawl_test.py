import sys
from playwright.sync_api import sync_playwright

url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    page.goto(url, timeout=20000)
    page.wait_for_timeout(5000)  # 챌린지 통과 대기

    html = page.content()
    print(html[:1500])

    with open("result.html", "w", encoding="utf-8") as f:
        f.write(html)

    browser.close()
