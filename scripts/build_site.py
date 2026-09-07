#!/usr/bin/env python3
"""
검색엔진이 읽을 수 있는 정적 페이지를 만든다.

메인 화면은 자바스크립트로 데이터를 불러오는데, 네이버 검색봇은
자바스크립트를 실행하지 않아 빈 페이지로 본다. 그래서
  1) 단지마다 정적 HTML 페이지를 만들고
  2) 메인 아래쪽에 그 페이지들로 가는 목록을 심고
  3) sitemap.xml / robots.txt 를 만든다.

수집(collect.py) 직후에 실행한다.
"""
import html, json, os, re, sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://cheongyak.day"
APT_DIR = os.path.join(ROOT, "apt")

DOW = ["월", "화", "수", "목", "금", "토", "일"]


def esc(v):
    return html.escape(str(v if v is not None else ""), quote=True)


def won(v):
    return f"{v/10000:.1f}".rstrip("0").rstrip(".") + "억" if v >= 10000 else f"{v:,}만"


def slug(name, key):
    """단지명을 URL 로 쓸 수 있게 다듬는다. 한글은 그대로 둔다(한국어 검색에 유리)."""
    s = re.sub(r"[^0-9A-Za-z가-힣]+", "-", str(name)).strip("-")
    return f"{s[:40]}-{key}" if s else key


def type_name(u):
    """주택형 코드를 사람이 읽는 표기로. 메인 화면의 typeName() 과 같은 규칙."""
    m = re.search(r"([A-Za-z]+)\s*$", str(u.get("t") or ""))
    suffix = m.group(1).upper() if m else ""
    return f"{round(u['area'])}{suffix}" if u.get("area") else (u.get("t") or "-")


def unk(v):
    return v is None


def txt_resale(n):
    return "확인 필요" if unk(n["resale"]) else ("없음" if n["resale"] == 0 else f"{n['resale']}개월")


def txt_live(n):
    return "확인 필요" if unk(n["live"]) else ("없음" if n["live"] == 0 else f"{n['live']}년")


def jeonse_text(n):
    if unk(n["live"]):
        return "공고문 확인 필요"
    return "가능" if n["live"] == 0 else "불가"


def page(n, style, updated):
    """단지 하나의 상세 페이지"""
    units = n["units"]
    lo, hi = min(u["price"] for u in units), max(u["price"] for u in units)
    amin = min(u["area"] for u in units)
    amax = max(u["area"] for u in units)
    title = f"{n['name']} 청약 정보 · 분양가와 일정 | 청약달력"
    desc = (f"{n['region']} {n['district']} {n['name']} 청약 정보. "
            f"총 {n['total']:,}세대, 분양가 {won(lo)}~{won(hi)}, "
            f"전용 {amin:.0f}~{amax:.0f}㎡. 특별공급 {n['special']}, "
            f"전매제한 {txt_resale(n)}, 실거주의무 {txt_live(n)}.")
    url = f"{SITE}/apt/{n['_slug']}.html"

    rows = "\n".join(
        f'<tr><td class="hi">{esc(type_name(u))}</td><td class="n">{u["area"]:.2f}㎡</td>'
        f'<td class="n">{u["n"]:,}</td>'
        f'<td class="n">{"-" if u.get("gen") is None else format(u["gen"], ",")}</td>'
        f'<td class="n hi">{won(u["price"])}</td>'
        f'<td class="n">{round(u["price"]/(u["area"]/3.3058)):,}만</td></tr>'
        for u in units)

    sched = "".join(
        f"<div><dt>{lab}</dt><dd>{esc(n[k] or '-')}</dd></div>"
        for lab, k in [("입주자모집공고", "special"), ("특별공급", "special"),
                       ("1순위", "first"), ("2순위", "second"),
                       ("당첨자 발표", "result"), ("계약", "contract")][1:])

    notes = "".join(f"<li>{esc(t)}</li>" for t in n.get("notes", []))

    ld = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "청약달력", "item": SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": n["name"], "item": url},
        ],
    }, ensure_ascii=False)

    return f'''<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<html lang="ko">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="청약달력">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{url}">
<meta property="og:locale" content="ko_KR">
<meta name="twitter:card" content="summary">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500;600&family=IBM+Plex+Sans+KR:wght@400;500;600&family=Noto+Serif+KR:wght@600;700&display=optional">
{style}
<style>
.doc{{max-width:760px; margin:0 auto; padding:0 16px 60px}}
.crumb{{font-size:12.5px; color:var(--ink-3); margin:20px 0 6px}}
.crumb a{{color:var(--ink-3); text-decoration:none}}
.crumb a:hover{{text-decoration:underline}}
.doc h1{{font-family:"Noto Serif KR",serif; font-size:25px; margin:0 0 6px; letter-spacing:-.02em}}
.doc .where{{color:var(--ink-2); font-size:14.5px; margin:0 0 18px}}
.doc h2{{font-family:"Noto Serif KR",serif; font-size:17px; margin:30px 0 9px; font-weight:600}}
.doc p, .doc li{{color:var(--ink-2); font-size:14.5px; line-height:1.75}}
.keyfacts{{display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:1px;
  background:var(--line); border:1px solid var(--line); border-radius:var(--r); overflow:hidden}}
.keyfacts div{{background:var(--surface); padding:11px 13px}}
.keyfacts dt{{font-size:11.5px; color:var(--ink-3); margin:0}}
.keyfacts dd{{margin:3px 0 0; font-size:15.5px; font-weight:600; color:var(--ink);
  font-family:"IBM Plex Mono","IBM Plex Sans KR",monospace; letter-spacing:-.02em;
  white-space:nowrap}}
.doc .notes{{margin:12px 0 0; padding-left:18px}}
.doc .notes li{{margin-bottom:4px}}
.warn{{background:var(--warn-bg); color:var(--warn); border:1px solid color-mix(in srgb, var(--warn) 25%, transparent);
  border-radius:8px; padding:11px 14px; font-size:13px; margin:16px 0}}
.golink{{display:inline-block; margin-top:8px; background:var(--accent); color:#fff;
  text-decoration:none; font-size:14px; font-weight:500; padding:9px 18px; border-radius:8px}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]) .golink{{color:#0E1219}}}}
:root[data-theme="dark"] .golink{{color:#0E1219}}
.back{{display:inline-block; margin-top:34px; font-size:14px; color:var(--accent); text-decoration:none}}
</style>
<script type="application/ld+json">{ld}</script>

<header>
  <div class="wrap hd">
    <a class="logo" href="/" style="text-decoration:none">청약<b>달력</b></a>
    <span class="tag">분양가 · 세대수 · 전매제한 · 실거주의무를 날짜순으로</span>
  </div>
</header>

<main class="doc">
  <nav class="crumb"><a href="/">청약달력</a> › {esc(n["region"])} › {esc(n["name"])}</nav>
  <h1>{esc(n["name"])} 청약 정보</h1>
  <p class="where">{esc(n["region"])} {esc(n["district"])} · {esc(n["type"])}주택 · {esc(n["zone"])}
     {" · 시공 " + esc(n["builder"]) if n.get("builder") else ""}</p>

  <dl class="keyfacts">
    <div><dt>총 세대수</dt><dd>{n["total"]:,}</dd></div>
    <div><dt>일반공급</dt><dd>{n["general"]:,}</dd></div>
    <div><dt>분양가</dt><dd>{won(lo)}~{won(hi)}</dd></div>
    <div><dt>전용면적</dt><dd>{amin:.0f}~{amax:.0f}㎡</dd></div>
    <div><dt>전매제한</dt><dd>{txt_resale(n)}</dd></div>
    <div><dt>실거주의무</dt><dd>{txt_live(n)}</dd></div>
    <div><dt>전세</dt><dd>{jeonse_text(n)}</dd></div>
  </dl>

  <h2>평형별 공급 세대수와 분양가</h2>
  <div class="tblwrap"><table>
    <thead><tr><th>타입</th><th>전용면적</th><th>총 세대</th><th>일반공급</th><th>분양가</th><th>3.3㎡당</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
  <p style="font-size:12.5px; color:var(--ink-3); margin-top:8px">분양가는 최고가 기준이며 발코니 확장비는 별도입니다.</p>

  <h2>청약 일정</h2>
  <dl class="sched">{sched}</dl>

  <h2>전매제한과 실거주의무</h2>
  <p>이 단지는 전매제한 <b>{txt_resale(n)}</b>, 실거주의무 <b>{txt_live(n)}</b>입니다.
     따라서 입주 후 전세를 놓는 것은 <b>{jeonse_text(n)}</b>합니다.</p>
  <div class="warn">전매제한과 실거주의무는 입주자모집공고문에서 자동으로 읽어온 값입니다.
    계약 전에는 반드시 공고문 원문을 확인하세요.</div>

  {"<h2>참고</h2><ul class='notes'>" + notes + "</ul>" if notes else ""}

  <p><a class="golink" href="{esc(n["link"])}" target="_blank" rel="noopener">청약홈에서 공고문 보기 →</a></p>

  <a class="back" href="/">← 전체 청약 일정 보기</a>
  <footer style="margin-top:30px">데이터 기준 {updated} · 자료 출처 한국부동산원 청약홈 ·
    정보 제공 목적이며 법적 효력이 없습니다.
    <div style="margin-top:8px; display:flex; gap:14px; flex-wrap:wrap">
      <a href="/privacy.html">개인정보처리방침</a><a href="/contact.html">문의하기</a>
    </div>
  </footer>
</main>
'''


def main():
    src = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    style = re.search(r"<style>.*?</style>", src, re.S).group(0)

    data = json.load(open(os.path.join(ROOT, "data", "notices.json"), encoding="utf-8"))
    items = data["items"]
    updated = data.get("updated", str(date.today()))

    os.makedirs(APT_DIR, exist_ok=True)
    for f in os.listdir(APT_DIR):          # 지난 공고 페이지는 정리한다
        if f.endswith(".html"):
            os.remove(os.path.join(APT_DIR, f))

    for n in items:
        n["_slug"] = slug(n["name"], n["id"].split("-")[0])
        with open(os.path.join(APT_DIR, n["_slug"] + ".html"), "w", encoding="utf-8") as fp:
            fp.write(page(n, style, updated))
    print(f"단지 페이지 {len(items)}개 생성", file=sys.stderr)

    # 메인 아래쪽 정적 목록 (검색봇이 각 페이지를 찾아가는 통로)
    lis = "\n".join(
        f'<li><a href="/apt/{n["_slug"]}.html">{esc(n["name"])}</a>'
        f'<div class="meta">{esc(n["region"])} {esc(n["district"])} · 특별공급 {esc(n["special"])}</div></li>'
        for n in items)
    block = (f'<section class="alllist" id="alllist">\n'
             f'<h2>전체 청약 단지</h2>\n'
             f'<p class="sub">단지명을 누르면 분양가·평형별 공급·일정을 자세히 볼 수 있습니다. '
             f'({updated} 기준 {len(items)}곳)</p>\n<ul>\n{lis}\n</ul>\n</section>')
    out = re.sub(r'<section class="alllist" id="alllist">.*?</section>',
                 block, src, count=1, flags=re.S)
    if out == src:   # 아직 자리가 비어 있는 경우
        out = src.replace('<section class="alllist" id="alllist"></section>', block, 1)
    open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8").write(out)

    # sitemap.xml
    urls = [(SITE + "/", updated, "daily", "1.0"),
            (SITE + "/privacy.html", updated, "yearly", "0.2"),
            (SITE + "/contact.html", updated, "yearly", "0.2")]
    urls += [(f"{SITE}/apt/{n['_slug']}.html", updated, "weekly", "0.8") for n in items]
    body = "\n".join(
        f"  <url><loc>{u}</loc><lastmod>{m}</lastmod>"
        f"<changefreq>{c}</changefreq><priority>{p}</priority></url>"
        for u, m, c, p in urls)
    open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8").write(
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}\n</urlset>\n')

    open(os.path.join(ROOT, "robots.txt"), "w", encoding="utf-8").write(
        "User-agent: *\nAllow: /\n\n"
        "# 네이버\nUser-agent: Yeti\nAllow: /\n\n"
        f"Sitemap: {SITE}/sitemap.xml\n")

    print(f"sitemap {len(urls)}개 · robots.txt 생성", file=sys.stderr)


if __name__ == "__main__":
    main()
