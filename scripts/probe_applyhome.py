#!/usr/bin/env python3
"""
청약홈 상세 페이지에서 공고문 PDF를 어떻게 찾는지 확인하는 정찰 스크립트.

이 컨테이너에서는 청약홈 접근이 막혀 있어 GitHub Actions 러너에서 돌린다.
로그만 보면 다음 세 가지를 알 수 있다.
  1. 상세 페이지에 접근이 되는지 (봇 차단 여부)
  2. 공고문 PDF 링크가 어떤 형태인지
  3. PDF에서 전매제한·거주의무가 실제로 뽑히는지

사용법: python3 scripts/probe_applyhome.py 2026000364 [2026000358 ...]
"""
import os, re, ssl, sys, json
from urllib import request, parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pblanc_pdf

DETAIL = "https://www.applyhome.co.kr/ai/aia/selectAPTLttotPblancDetail.do"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def get(url, referer=None):
    req = request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/pdf,*/*",
        "Accept-Language": "ko-KR,ko;q=0.9",
        **({"Referer": referer} if referer else {}),
    })
    ctx = ssl.create_default_context()
    with request.urlopen(req, timeout=45, context=ctx) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()


def all_links(html, base):
    """필터 없이 페이지 안의 모든 링크·스크립트 이동 대상을 모은다."""
    hits = []
    for p in [r'href\s*=\s*["\']([^"\']+)["\']',
              r'onclick\s*=\s*["\']([^"\']+)["\']',
              r'location\.href\s*=\s*["\']([^"\']+)["\']',
              r'window\.open\s*\(\s*["\']([^"\']+)["\']',
              r'src\s*=\s*["\']([^"\']+)["\']']:
        hits += re.findall(p, html, re.I)
    seen, out = set(), []
    for h in hits:
        h = h.strip()
        if not h or h.startswith(("#", "javascript:void")): continue
        u = parse.urljoin(base, h) if not h.startswith("javascript:") else h
        if u not in seen:
            seen.add(u); out.append(u)
    return out


def find_links(html, base):
    """href / onclick / data-* 안에서 파일 다운로드로 보이는 후보를 모은다."""
    pats = [
        r'href\s*=\s*["\']([^"\']+)["\']',
        r'onclick\s*=\s*["\']([^"\']+)["\']',
        r'location\.href\s*=\s*["\']([^"\']+)["\']',
        r'src\s*=\s*["\']([^"\']+)["\']',
    ]
    hits = []
    for p in pats:
        hits += re.findall(p, html, re.I)
    keys = ("pdf", "download", "file", "atch", "pblanc", "popup", "view")
    out = []
    for h in hits:
        low = h.lower()
        if any(k in low for k in keys):
            out.append(parse.urljoin(base, h.strip()))
    seen, uniq = set(), []
    for u in out:
        if u not in seen:
            seen.add(u); uniq.append(u)
    return uniq


def probe(no):
    url = f"{DETAIL}?houseManageNo={no}&pblancNo={no}"
    print(f"\n{'='*70}\n[공고 {no}] {url}")
    try:
        st, ct, body = get(url)
    except Exception as e:
        print(f"  ✗ 상세 페이지 접근 실패: {e}")
        return
    print(f"  ✓ HTTP {st} · {ct} · {len(body):,} bytes")
    html = body.decode("utf-8", "replace")

    title = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    if title:
        print(f"  제목: {title.group(1).strip()[:70]}")

    # 페이지 안에 전매/거주 문구가 바로 있는지도 확인 (PDF 없이 끝날 수도 있다)
    plain = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    plain = re.sub(r"<[^>]+>", " ", plain)
    direct = pblanc_pdf.parse_text(plain)
    print(f"  상세 페이지 HTML 자체에서 파싱: {direct}")
    for kw in ("전매", "거주의무", "실거주"):
        for m in list(re.finditer(kw, plain))[:2]:
            print(f"    …{plain[max(0,m.start()-45):m.start()+75].strip()[:120]}…")

    links = find_links(html, url)
    print(f"  파일 후보 링크 {len(links)}개:")
    for u in links[:25]:
        print(f"    - {u}")

    if not links:
        # LH 공공분양처럼 청약홈에 첨부가 없는 경우, 페이지의 모든 링크를 살펴본다
        every = all_links(html, url)
        print(f"  ── 첨부가 없어 전체 링크 {len(every)}개를 확인합니다 ──")
        for u in every[:35]:
            print(f"    · {u[:150]}")
        for kw in ("공고문", "모집공고", "바로가기", "lh.or.kr", "청약플러스"):
            for m in list(re.finditer(kw, html))[:2]:
                seg = re.sub(r"\s+", " ", html[max(0, m.start()-160): m.start()+160])
                print(f"    [{kw}] …{seg}…")

    for u in links:
        if not any(k in u.lower() for k in ("pdf", "download", "file", "atch")):
            continue
        try:
            st, ct, body = get(u, referer=url)
        except Exception as e:
            print(f"  ✗ {u[:80]} → {e}")
            continue
        is_pdf = body[:5] == b"%PDF-" or "pdf" in ct.lower()
        print(f"  {'✓ PDF' if is_pdf else '· 비PDF'} {st} {ct} {len(body):,}B  {u[:80]}")
        if is_pdf:
            open("probe.pdf", "wb").write(body)
            try:
                result = pblanc_pdf.parse_pdf("probe.pdf")
                print(f"    ▶ 파싱 결과: {result}")

                # 실제로 어떤 표를 읽었는지 보여준다 (파싱이 틀렸을 때 원인 파악용)
                tables = pblanc_pdf.pdf_tables("probe.pdf")
                print(f"    표 {len(tables)}개 발견. 관련 표:")
                shown = 0
                for t in tables:
                    flat = " ".join(str(c or "") for row in t for c in row)
                    if "전매제한" in flat.replace(" ", "") and shown < 2:
                        for row in t[:4]:
                            print(f"      | " + " | ".join((str(c or "").replace(chr(10), " "))[:18] for c in row))
                        print("      " + "-" * 40)
                        shown += 1
                if not shown:
                    print("      (전매제한이 든 표를 못 찾음 → 본문 텍스트로 처리)")
                    text = pblanc_pdf.pdf_text("probe.pdf", max_pages=25)
                    for kw in ("전매제한", "거주의무"):
                        for m in list(re.finditer(kw, text))[:2]:
                            print(f"      …{text[max(0,m.start()-50):m.start()+90].replace(chr(10),' ')}…")
            except Exception as e:
                print(f"    ✗ PDF 파싱 실패: {e}")
            return


if __name__ == "__main__":
    nos = sys.argv[1:] or ["2026820006", "2026000409", "2026000414"]
    for n in nos:
        probe(n)
