import sys
import requests

url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"

res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
print("status:", res.status_code)
print(res.text[:500])

with open("result.html", "w", encoding="utf-8") as f:
    f.write(res.text)
