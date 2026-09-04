#!/usr/bin/env python3
"""
분양24(reby24.com) 사이트 구조 조사.

우리 사이트에 참고할 만한 부분이 있는지 보기 위한 일회성 조사 도구다.
공개 페이지 몇 개만 읽고, robots.txt 를 먼저 확인해 출력한다.
"""
import re, ssl, sys
from urllib import request, parse

BASE = "https://www.reby24.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def get(url):
    req = request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9",
        "Accept": "text/html,application/xhtml+xml,*/*"})
    with request.urlopen(req, timeout=40, context=ssl.create_default_context()) as r:
        return r.status, dict(r.headers), r.read()


def text_of(html):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def show(path, dump_text=0, dump_links=0):
    url = path if path.startswith("http") else BASE + path
    print(f"\n{'='*72}\n[{url}]")
    try:
        st, hdr, body = get(url)
    except Exception as e:
        print(f"  ✗ {e}"); return None
    html = body.decode("utf-8", "replace")
    print(f"  HTTP {st} · {hdr.get('Content-Type','')} · {len(body):,}B")
    for k in ("Server", "X-Powered-By", "Set-Cookie"):
        if hdr.get(k): print(f"  {k}: {str(hdr[k])[:110]}")

    # 어떤 도구로 만들었는지 단서
    for pat, label in [
        (r'<meta[^>]+name=["\']generator["\'][^>]*>', "generator 메타"),
        (r'<title[^>]*>(.*?)</title>', "제목"),
        (r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']{0,150})', "설명"),
    ]:
        m = re.search(pat, html, re.S | re.I)
        if m:
            got = re.sub(r"\s+", " ", m.group(0))[:180]
            print(f"  {label}: {got}")

    hints = {}
    for kw in ("imweb", "cafe24", "wordpress", "wp-content", "tistory", "gnuboard",
               "nextjs", "_next", "react", "vue", "jquery", "googlesyndication",
               "adsbygoogle", "google-analytics", "gtag", "kakao", "naver",
               "cloudflare", "aws", "firebase", "sitemap"):
        n = len(re.findall(kw, html, re.I))
        if n: hints[kw] = n
    print(f"  기술 단서: {hints}")

    if dump_text:
        print(f"  본문: {text_of(html)[:dump_text]}")
    if dump_links:
        hrefs = re.findall(r'href\s*=\s*["\']([^"\']+)["\']', html, re.I)
        uniq, seen = [], set()
        for h in hrefs:
            u = parse.urljoin(url, h.strip())
            if u.startswith(BASE) and u not in seen:
                seen.add(u); uniq.append(u)
        print(f"  내부 링크 {len(uniq)}개 (상위 {dump_links}):")
        for u in uniq[:dump_links]:
            print(f"    · {u[:140]}")
        return uniq
    return []


def main():
    print("### robots.txt / sitemap 먼저 확인")
    for p in ("/robots.txt", "/sitemap.xml"):
        try:
            st, hdr, body = get(BASE + p)
            print(f"\n[{p}] HTTP {st} · {len(body):,}B")
            print(body.decode("utf-8", "replace")[:700])
        except Exception as e:
            print(f"[{p}] ✗ {e}")

    show("/", dump_links=30)
    links = show("/recruit", dump_text=900, dump_links=40) or []

    # 상세 페이지로 보이는 링크 하나를 열어본다
    detail = next((u for u in links
                   if re.search(r"/(recruit|sale|site)[^/]*/[^/?]+", u) and "category=" not in u), None)
    if detail:
        show(detail, dump_text=2500, dump_links=25)
    else:
        print("\n(상세 페이지로 보이는 링크를 목록에서 찾지 못했습니다)")


if __name__ == "__main__":
    main()
