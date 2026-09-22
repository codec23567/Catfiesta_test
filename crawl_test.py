#!/usr/bin/env python3
"""
crawl_test.py
-------------
특정 사이트를 GitHub Actions(또는 서버 환경)에서 크롤링할 수 있는지
사전 진단하는 범용 스크립트.

체크 항목:
1. robots.txt 확인 (크롤링 허용 여부, 참고용)
2. 일반 requests로 HTML 가져오기 시도 (여러 User-Agent 로테이션)
3. 응답 상태코드 / 차단 여부 판단 (403, 429, Cloudflare 챌린지 등)
4. 받아온 HTML이 "정적으로 의미 있는 내용"을 담고 있는지 간단 검사
   (JS 렌더링이 필요한 SPA인지 추정)
5. 결과를 파일로 저장 (raw_response.html) 하여 직접 확인 가능

사용법:
    python3 crawl_test.py https://example.com
    python3 crawl_test.py https://example.com --save output.html
    python3 crawl_test.py https://example.com --timeout 15
"""

import argparse
import re
import sys
import time
import urllib.robotparser
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    print("[!] requests 라이브러리가 필요합니다: pip install requests")
    sys.exit(1)


# 여러 브라우저를 흉내내는 User-Agent 목록 (차단 회피 테스트용)
USER_AGENTS = [
    # Chrome (Windows)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome (Mac)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Safari (Mac)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    # Firefox
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

BLOCK_SIGNATURES = [
    "cloudflare", "captcha", "access denied", "are you a robot",
    "unusual traffic", "attention required", "just a moment",
    "cf-browser-verification", "perimeterx", "akamai",
]


def check_robots(url: str, timeout: int):
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    print(f"\n[1] robots.txt 확인: {robots_url}")
    try:
        resp = requests.get(robots_url, timeout=timeout,
                             headers={"User-Agent": USER_AGENTS[0]})
        if resp.status_code == 200:
            rp.parse(resp.text.splitlines())
            allowed = rp.can_fetch("*", url)
            print(f"    -> 상태코드 200, 대상 URL 크롤링 허용 여부(참고용): {allowed}")
            if not allowed:
                print("    ※ robots.txt는 '요청'일 뿐 강제성은 없지만, "
                      "상업적/공개 서비스에서는 준수를 권장합니다.")
        else:
            print(f"    -> robots.txt 없음 또는 접근 불가 (status={resp.status_code})")
    except requests.RequestException as e:
        print(f"    -> robots.txt 요청 실패: {e}")


def detect_block(status_code: int, text: str):
    reasons = []
    if status_code in (403, 401):
        reasons.append(f"HTTP {status_code} (권한/차단 가능성)")
    if status_code == 429:
        reasons.append("HTTP 429 (Rate limit)")
    if status_code >= 500:
        reasons.append(f"HTTP {status_code} (서버 오류)")

    lowered = text.lower()
    for sig in BLOCK_SIGNATURES:
        if sig in lowered:
            reasons.append(f"차단 의심 키워드 발견: '{sig}'")
    return reasons


def looks_like_spa(html: str) -> bool:
    """정적 HTML에 의미있는 콘텐츠가 거의 없고 JS 번들만 있는 경우 True"""
    body_match = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL | re.IGNORECASE)
    body = body_match.group(1) if body_match else html
    visible_text = re.sub(r"<[^>]+>", "", body).strip()

    has_root_div = bool(re.search(r'id=["\'](app|root|__next)["\']', html, re.IGNORECASE))
    script_count = len(re.findall(r"<script", html, re.IGNORECASE))

    return (len(visible_text) < 200 and has_root_div) or (len(visible_text) < 50 and script_count > 3)


def try_fetch(url: str, timeout: int):
    print(f"\n[2] HTML 요청 시도: {url}")
    last_result = None

    for i, ua in enumerate(USER_AGENTS, 1):
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
        }
        try:
            start = time.time()
            resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            elapsed = time.time() - start
            print(f"    UA #{i} -> status={resp.status_code}, "
                  f"길이={len(resp.text)}자, {elapsed:.2f}초, "
                  f"최종 URL={resp.url}")

            reasons = detect_block(resp.status_code, resp.text)
            last_result = resp

            if resp.status_code == 200 and not reasons:
                print(f"    -> UA #{i}로 성공적으로 응답 받음")
                return resp, reasons
            elif reasons:
                print(f"    -> 의심 사유: {', '.join(reasons)}")

        except requests.RequestException as e:
            print(f"    UA #{i} -> 요청 실패: {e}")

        time.sleep(1)  # 과도한 연속 요청 방지

    return last_result, (detect_block(last_result.status_code, last_result.text) if last_result else ["모든 시도 실패"])


def main():
    parser = argparse.ArgumentParser(description="사이트 크롤링 가능 여부 진단")
    parser.add_argument("url", help="테스트할 URL (예: https://example.com)")
    parser.add_argument("--timeout", type=int, default=10, help="요청 타임아웃(초), 기본 10")
    parser.add_argument("--save", default="raw_response.html", help="저장할 HTML 파일명")
    args = parser.parse_args()

    print("=" * 60)
    print(f"대상 URL: {args.url}")
    print("=" * 60)

    check_robots(args.url, args.timeout)
    resp, reasons = try_fetch(args.url, args.timeout)

    print("\n[3] 결과 요약")
    print("-" * 60)

    if resp is None:
        print("❌ 요청 자체가 모두 실패했습니다. 네트워크/URL을 확인하세요.")
        sys.exit(1)

    with open(args.save, "w", encoding="utf-8") as f:
        f.write(resp.text)
    print(f"    HTML 저장 완료 -> {args.save} ({len(resp.text)}자)")

    if resp.status_code == 200 and not reasons:
        print("✅ 정상적으로 HTML을 받아왔습니다 (단순 requests로 크롤링 가능해 보임).")
    elif reasons:
        print("⚠️  차단되었거나 의심스러운 응답입니다:")
        for r in reasons:
            print(f"    - {r}")
        print("    -> Cloudflare/차단이면 Playwright(헤드리스 브라우저) 또는 "
              "프록시/헤더 조정이 필요할 수 있습니다.")
    else:
        print(f"⚠️  애매한 상태코드({resp.status_code})입니다. 저장된 HTML을 직접 확인하세요.")

    if looks_like_spa(resp.text):
        print("\n📌 참고: 받아온 HTML에 실제 콘텐츠가 거의 없어 보입니다.")
        print("   -> React/Vue 등 SPA로 추정되며, JS 렌더링 후의 결과가 필요할 수 있습니다.")
        print("   -> 이 경우 requests/curl 대신 Playwright, Puppeteer, Selenium 등이 필요합니다.")

    print("\n완료.")


if __name__ == "__main__":
    main()
