#!/usr/bin/env python3
"""
검색엔진이 읽을 수 있는 정적 페이지를 만든다.

메인 화면은 자바스크립트로 데이터를 불러오는데, 네이버 검색봇은
자바스크립트를 실행하지 않아 빈 페이지로 본다. 그래서
  1) 단지마다 정적 HTML 페이지를 만들고
  2) 메인 아래쪽에 그 페이지들로 가는 목록을 심고
  3) sitemap.xml / robots.txt / 404.html 을 만든다.

수집 목록에서 빠진(접수가 끝난) 단지도 페이지를 지우지 않는다.
단지명 검색은 당첨 발표·계약·입주 때까지 계속 들어오기 때문이다.
data/archive.json 에 보관해 두고 "청약 마감" 표시를 붙여 계속 만든다.

수집(collect.py) 직후에 실행한다.
"""
import glob, html, json, os, re, sys
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://cheongyak.day"
APT_DIR = os.path.join(ROOT, "apt")
ARCHIVE = os.path.join(ROOT, "data", "archive.json")
# 주소는 확장자 없이 쓴다. Cloudflare Pages 가 .html 주소를 확장자 없는 주소로
# 308 리다이렉트하므로, canonical·sitemap 에 .html 을 쓰면 구글이 두 주소를 서로의
# 대체 페이지로 보고 어느 쪽도 색인하지 않는다(2026-11 서치콘솔 경고).

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
    jt = jeonse_text(n)
    closed = n.get("_closed")
    tail = "전세 가능" if jt == "가능" else ("전세 불가" if jt == "불가" else "분양가와 일정")
    title = f"{n['name']} 청약 정보 · {tail} | 청약달력"
    desc = (f"{n['region']} {n['district']} {n['name']} 청약 정보{' (청약 마감)' if closed else ''}. "
            f"총 {n['total']:,}세대, 분양가 {won(lo)}~{won(hi)}, "
            f"전용 {amin:.0f}~{amax:.0f}㎡. 특별공급 {n['special']}, "
            f"전매제한 {txt_resale(n)}, 실거주의무 {txt_live(n)}, 입주 후 전세 {jt}.")
    url = f"{SITE}/apt/{n['_slug']}"

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

    banner = (f'<div class="closed"><b>청약 마감</b> 이 단지는 청약 접수가 끝났습니다. '
              f'당첨자 발표 {esc(n["result"] or "-")} · 계약 {esc(n["contract"] or "-")}. '
              f'지금 접수 중인 단지는 <a href="/">전체 청약 일정</a>에서 볼 수 있습니다.</div>'
              if closed else "")

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
.closed{{background:var(--off-bg); color:var(--ink-2); border-radius:8px; padding:11px 14px;
  font-size:13.5px; line-height:1.7; margin:0 0 18px}}
.closed b{{color:var(--off); margin-right:6px}}
.closed a{{color:var(--accent)}}
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
  {banner}

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
  <footer style="margin-top:30px">데이터 기준 {closed or updated} · 자료 출처 한국부동산원 청약홈 ·
    정보 제공 목적이며 법적 효력이 없습니다.
    <div style="margin-top:8px; display:flex; gap:14px; flex-wrap:wrap">
      <a href="/privacy">개인정보처리방침</a><a href="/contact">문의하기</a>
    </div>
  </footer>
</main>
'''



def jeonse_page(items, style, updated):
    """실거주의무·전세 가능 여부를 주제로 한 전용 페이지.

    "실거주의무 없는 아파트", "분양 전세 가능" 같은 검색어를 정면으로 받는다.
    청약홈 OpenAPI 에는 이 항목이 없어 대부분의 청약 사이트가 목록으로 보여주지 못한다.
    """
    ok = [n for n in items if n["live"] == 0]
    no = [n for n in items if n["live"] and n["live"] > 0]
    unknown = [n for n in items if n["live"] is None]

    def rows(group):
        return "\n".join(
            f'<tr><td class="hi"><a href="/apt/{n["_slug"]}">{esc(n["name"])}</a></td>'
            f'<td>{esc(n["region"])} {esc(n["district"])}</td>'
            f'<td class="n">{txt_resale(n)}</td>'
            f'<td class="n">{txt_live(n)}</td>'
            f'<td class="n">{esc(n["special"] or "-")}</td></tr>'
            for n in group)

    def block(title, group, note, cls):
        if not group:
            return ""
        return (f'<h2>{title} <span class="cnt {cls}">{len(group)}곳</span></h2>'
                f'<p>{note}</p>'
                f'<div class="tblwrap"><table>'
                f'<thead><tr><th>단지명</th><th>위치</th><th>전매제한</th>'
                f'<th>실거주의무</th><th>특별공급</th></tr></thead>'
                f'<tbody>{rows(group)}</tbody></table></div>')

    title = "전세 놓을 수 있는 청약 단지 · 실거주의무 없는 분양 아파트 | 청약달력"
    desc = (f"분양받은 아파트에 전세를 놓을 수 있는지 한눈에 확인하세요. "
            f"{updated} 기준 실거주의무가 없어 전세가 가능한 단지 {len(ok)}곳을 정리했습니다. "
            f"단지별 전매제한 기간도 함께 표시합니다.")
    url = SITE + "/jeonse"

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
.doc{{max-width:820px; margin:0 auto; padding:0 16px 60px}}
.crumb{{font-size:12.5px; color:var(--ink-3); margin:20px 0 6px}}
.crumb a{{color:var(--ink-3); text-decoration:none}}
.doc h1{{font-family:"Noto Serif KR",serif; font-size:26px; margin:0 0 8px; letter-spacing:-.02em;
  text-wrap:balance}}
.doc .lead{{color:var(--ink-2); font-size:15px; margin:0 0 22px; line-height:1.7}}
.doc h2{{font-family:"Noto Serif KR",serif; font-size:18px; margin:34px 0 6px; font-weight:600}}
.doc p, .doc li{{color:var(--ink-2); font-size:14.5px; line-height:1.75}}
.cnt{{font-family:"IBM Plex Sans KR",sans-serif; font-size:12.5px; font-weight:500;
  padding:2px 9px; border-radius:99px; vertical-align:middle; margin-left:4px}}
.cnt.ok{{background:var(--ok-bg); color:var(--ok)}}
.cnt.no{{background:var(--warn-bg); color:var(--warn)}}
.cnt.unk{{background:var(--off-bg); color:var(--off)}}
.doc table a{{color:var(--ink); text-decoration:none}}
.doc table a:hover{{color:var(--accent); text-decoration:underline}}
.doc td{{text-align:left}}
.doc td.n{{text-align:right}}
.explain{{background:var(--surface); border:1px solid var(--line); border-radius:var(--r);
  padding:16px 18px; margin:26px 0}}
.explain h3{{font-size:15px; margin:0 0 6px; font-weight:600; color:var(--ink)}}
.explain h3+p{{margin-top:0}}
.explain p:last-child{{margin-bottom:0}}
.warn{{background:var(--warn-bg); color:var(--warn);
  border:1px solid color-mix(in srgb, var(--warn) 25%, transparent);
  border-radius:8px; padding:12px 15px; font-size:13.5px; margin:20px 0}}
.back{{display:inline-block; margin-top:32px; font-size:14px; color:var(--accent); text-decoration:none}}
</style>

<header>
  <div class="wrap hd">
    <a class="logo" href="/" style="text-decoration:none">청약<b>달력</b></a>
    <span class="tag">분양가 · 세대수 · 전매제한 · 실거주의무를 날짜순으로</span>
  </div>
</header>

<main class="doc">
  <nav class="crumb"><a href="/">청약달력</a> › 실거주의무와 전세</nav>
  <h1>전세 놓을 수 있는 청약 단지</h1>
  <p class="lead">분양받은 아파트에 <b>실거주의무가 없으면 입주 후 전세를 놓을 수 있습니다.</b>
    이 정보는 청약홈 공공데이터에 들어 있지 않아 입주자모집공고문을 직접 열어봐야 알 수 있습니다.
    청약달력은 공고문에서 이 값을 읽어와 단지별로 정리합니다.
    <b>{updated} 기준 {len(items)}곳</b>을 확인했습니다.</p>

  {block("전세 가능", ok, "실거주의무가 없어 입주 후 임대를 놓을 수 있는 단지입니다. 다만 전매제한 기간에는 분양권 자체를 팔 수 없습니다.", "ok")}
  {block("전세 불가", no, "실거주의무 기간에는 본인이 직접 거주해야 하며 임대를 놓을 수 없습니다.", "no")}
  {block("공고문 확인 필요", unknown, "공고문에서 값을 읽지 못한 단지입니다. 단지명을 눌러 공고문 원문을 확인하세요.", "unk")}

  <div class="explain">
    <h3>실거주의무란</h3>
    <p>분양가상한제가 적용되는 주택 등에 붙는 의무로, 당첨자가 일정 기간 그 집에
      직접 살아야 하는 규정입니다. 이 기간에는 전세나 월세를 놓을 수 없습니다.</p>
    <h3>전매제한과 무엇이 다른가</h3>
    <p><b>전매제한</b>은 분양권이나 주택을 <b>파는 것</b>을 막는 규정이고,
      <b>실거주의무</b>는 <b>남에게 빌려주는 것</b>을 막는 규정입니다.
      전매제한만 있고 실거주의무가 없다면, 팔 수는 없어도 전세를 놓는 것은 가능합니다.</p>
    <h3>왜 다른 곳에서는 보기 어려운가</h3>
    <p>한국부동산원 청약홈이 공개하는 분양정보 API에는 이 두 항목이 포함되어 있지 않습니다.
      입주자모집공고문 PDF 안의 표에만 들어 있어, 대부분의 청약 정보 서비스는
      목록에서 이 값을 보여주지 못합니다.</p>
  </div>

  <div class="warn">여기 표시된 값은 입주자모집공고문에서 자동으로 읽어온 것입니다.
    제도는 개정될 수 있고 단지별 예외도 있으므로, 계약 전에는 반드시 공고문 원문과
    사업주체에 확인하시기 바랍니다. 본 페이지는 정보 제공 목적이며 법률 자문이 아닙니다.</div>

  <a class="back" href="/">← 전체 청약 일정 보기</a>
  <footer style="margin-top:30px">데이터 기준 {updated} · 자료 출처 한국부동산원 청약홈
    <div style="margin-top:8px; display:flex; gap:14px; flex-wrap:wrap">
      <a href="/privacy">개인정보처리방침</a><a href="/contact">문의하기</a>
    </div>
  </footer>
</main>
'''

OUTLOOK_CLS = {"상승": "up", "하락": "down", "보합": "flat", "혼조": "mix", "판단 없음": "none"}

# 주간 요약은 메인과 따로 디자인한다(넓은 여백, 큰 제목, 연회색 위 둥근 카드).
# 한글 웹폰트를 기다리면 레이아웃이 밀리므로 시스템 폰트만 쓴다.
TREND_CSS = """
:root{
  --bg:#FFFFFF; --band:#F5F5F7; --card:#FFFFFF; --ink:#1D1D1F; --ink-2:#424245; --ink-3:#6E6E73;
  --line:#D2D2D7; --link:#0066CC;
  --up:#D70015; --up-bg:#FDEBEC; --down:#0071E3; --down-bg:#E8F1FD;
  --mix:#B64400; --mix-bg:#FDF0E6; --none:#6E6E73; --none-bg:#EDEDF0;
  --nav:rgba(255,255,255,.72);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#000000; --band:#101012; --card:#1D1D1F; --ink:#F5F5F7; --ink-2:#D2D2D7; --ink-3:#86868B;
    --line:#424245; --link:#2997FF;
    --up:#FF6961; --up-bg:#3A1618; --down:#2997FF; --down-bg:#0E2440;
    --mix:#FF9F45; --mix-bg:#3A2410; --none:#A1A1A6; --none-bg:#2C2C2E;
    --nav:rgba(22,22,23,.72);
  }
}
:root[data-theme="dark"]{
  --bg:#000000; --band:#101012; --card:#1D1D1F; --ink:#F5F5F7; --ink-2:#D2D2D7; --ink-3:#86868B;
  --line:#424245; --link:#2997FF;
  --up:#FF6961; --up-bg:#3A1618; --down:#2997FF; --down-bg:#0E2440;
  --mix:#FF9F45; --mix-bg:#3A2410; --none:#A1A1A6; --none-bg:#2C2C2E;
  --nav:rgba(22,22,23,.72);
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0; background:var(--bg); color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic","Segoe UI",sans-serif;
  font-size:17px; line-height:1.55; letter-spacing:-.01em; -webkit-font-smoothing:antialiased;
  word-break:keep-all; overflow-wrap:break-word}
a{color:var(--link); text-decoration:none}
a:hover{text-decoration:underline}
.in{max-width:980px; margin:0 auto; padding:0 22px}

.nav{position:sticky; top:0; z-index:10; background:var(--nav);
  -webkit-backdrop-filter:saturate(180%) blur(20px); backdrop-filter:saturate(180%) blur(20px);
  border-bottom:1px solid color-mix(in srgb, var(--line) 50%, transparent)}
.nav .in{display:flex; align-items:center; justify-content:space-between; height:48px}
.nav .logo{color:var(--ink); font-weight:600; font-size:17px; letter-spacing:-.02em}
.nav .logo:hover{text-decoration:none}
.nav .links{display:flex; gap:22px; font-size:13px}
.nav .links a{color:var(--ink-2)}

.hero{text-align:center; padding:84px 0 64px}
.eyebrow{font-size:17px; font-weight:600; color:var(--up); margin:0 0 10px}
.hero h1{font-size:clamp(32px, 5.4vw, 56px); line-height:1.08; font-weight:700;
  letter-spacing:-.035em; margin:0 auto; max-width:860px; text-wrap:balance}
.hero .span{font-size:15px; color:var(--ink-3); margin:18px 0 0}
.hero .lead{font-size:clamp(19px, 2.2vw, 22px); line-height:1.5; color:var(--ink-2);
  max-width:720px; margin:28px auto 0; text-wrap:pretty}

.band{background:var(--band); padding:80px 0}
.band h2, .vids h2{font-size:clamp(28px, 4vw, 40px); font-weight:700; letter-spacing:-.03em;
  line-height:1.1; margin:0 0 8px; text-align:center}
.band .sub, .vids .sub{text-align:center; color:var(--ink-3); font-size:17px; margin:0 0 44px}

.stats{display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:16px}
.stat{background:var(--card); border-radius:18px; padding:26px 24px; text-align:center}
.stat .n{font-size:56px; font-weight:700; letter-spacing:-.04em; line-height:1; font-variant-numeric:tabular-nums}
.stat .l{font-size:15px; color:var(--ink-3); margin-top:8px}
.stat.up .n{color:var(--up)} .stat.down .n{color:var(--down)}
.stat.mix .n{color:var(--mix)} .stat.flat .n, .stat.none .n{color:var(--none)}
.meter{display:flex; height:8px; border-radius:99px; overflow:hidden; gap:3px; margin:26px auto 0; max-width:640px}
.meter i{display:block} .meter .up{background:var(--up)} .meter .down{background:var(--down)}
.meter .mix{background:var(--mix)} .meter .flat, .meter .none{background:var(--none); opacity:.5}

.cols{display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:16px; margin-top:64px}
.col{background:var(--card); border-radius:18px; padding:30px 28px}
.col h3{font-size:21px; font-weight:700; letter-spacing:-.02em; margin:0 0 14px}
.col ul{margin:0; padding:0; list-style:none}
.col li{font-size:15px; line-height:1.6; color:var(--ink-2); padding:12px 0;
  border-top:1px solid color-mix(in srgb, var(--line) 60%, transparent)}
.col li:first-child{border-top:0; padding-top:0}

.vids{padding:96px 0}
.grid{display:grid; grid-template-columns:repeat(auto-fill, minmax(min(420px, 100%), 1fr)); gap:20px}
.v{background:var(--band); border-radius:22px; padding:30px 30px 26px; display:flex; flex-direction:column; min-width:0}
.v .who{display:flex; align-items:center; justify-content:space-between; gap:10px;
  font-size:13px; color:var(--ink-3)}
.v .who b{color:var(--ink); font-weight:600; font-size:14px}
.pill{flex:none; font-size:12px; font-weight:600; padding:4px 11px; border-radius:99px}
.pill.up{color:var(--up); background:var(--up-bg)} .pill.down{color:var(--down); background:var(--down-bg)}
.pill.mix{color:var(--mix); background:var(--mix-bg)} .pill.flat, .pill.none{color:var(--none); background:var(--none-bg)}
.v h3{font-size:21px; line-height:1.35; font-weight:700; letter-spacing:-.025em; margin:14px 0 14px; text-wrap:pretty}
.v ul{margin:0; padding-left:18px; color:var(--ink-2); font-size:15px; line-height:1.6}
.v li{margin:0 0 8px}
.v .adv{font-size:14px; color:var(--ink-2); background:var(--card); border-radius:12px; padding:12px 14px; margin:8px 0 0}
.v .adv b{color:var(--ink)}
.v .tags{display:flex; flex-wrap:wrap; gap:6px; margin-top:14px}
.v .tags span{font-size:12px; color:var(--ink-3); background:var(--card); padding:4px 10px; border-radius:99px}
.v .tags a{font-size:12px; background:var(--card); padding:4px 10px; border-radius:99px}
.v .go{margin-top:auto; padding-top:20px; font-size:15px; display:flex; gap:8px; align-items:baseline}
.v .go b{flex:none; font-weight:400; white-space:nowrap}
.v .go span{color:var(--ink-3); font-size:13px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; min-width:0}

.foot{border-top:1px solid color-mix(in srgb, var(--line) 60%, transparent); padding:22px 0 48px;
  font-size:12px; line-height:1.7; color:var(--ink-3)}
.foot p{margin:0 0 8px}

@media (max-width:640px){
  .in{padding:0 16px}
  .hero{padding:56px 0 44px}
  .band, .vids{padding:56px 0}
  .stats{grid-template-columns:repeat(2, 1fr); gap:12px}
  .stat{padding:20px 12px} .stat .n{font-size:44px}
  .cols{margin-top:40px}
  .grid{grid-template-columns:1fr}
  .v{padding:24px 20px 20px; border-radius:18px}
  .nav .links a:not(:first-child){display:none}
}
"""


def trend_page(d, videos, apts):
    """부동산 유튜버 주간 요약 (scripts/yt_trend.py 가 만든 data/yt/ 를 읽는다).

    유튜버별 요약을 나열하는 데서 그치지 않고, 맨 위에 의견 분포와 종합을 둔다.
    요약만 늘어놓은 페이지는 구글이 저품질 대량 생성물로 보기 쉽다.
    """
    made = datetime.fromisoformat(d["made"])
    start = made - timedelta(days=7)
    span = f"{start.month}월 {start.day}일 – {made.month}월 {made.day}일"
    url = f"{SITE}/trend/{d['week']}"
    title = f"부동산 유튜버 주간 요약 ({span}) | 청약달력"
    desc = f"{span} 주요 부동산 유튜브 채널의 시장 전망을 한눈에. {d['overview'][:90]}"

    norm = lambda s: re.sub(r"\s+", "", s)
    def apt_link(name):
        for n in apts:
            if norm(name) and (norm(name) in norm(n["name"]) or norm(n["name"]) in norm(name)):
                return f'<a href="/apt/{n["_slug"]}">{esc(name)}</a>'
        return f"<span>{esc(name)}</span>"

    cnt = d["outlook_count"]
    shown = [k for k in OUTLOOK_CLS if cnt.get(k)]
    stats = "".join(f'<div class="stat {OUTLOOK_CLS[k]}"><div class="n">{cnt[k]}</div>'
                    f'<div class="l">{k}</div></div>' for k in shown)
    meter = "".join(f'<i class="{OUTLOOK_CLS[k]}" style="flex:{cnt[k]}"></i>' for k in shown)
    channels = len({v["channel"] for v in videos})

    def li(xs):
        return "".join(f"<li>{esc(x)}</li>" for x in xs)

    cards = []
    for v in videos:
        s = v["summary"]
        tags = "".join(apt_link(c) for c in s["complexes"][:6])
        tags += "".join(f"<span>{esc(r)}</span>" for r in s["regions"][:6])
        cards.append(f'''<article class="v">
  <div class="who"><div><b>{esc(v["channel"])}</b> · {esc(s["speaker"])}</div>
    <span class="pill {OUTLOOK_CLS.get(s["outlook"], "none")}">{esc(s["outlook"])}</span></div>
  <h3>{esc(s["headline"])}</h3>
  <ul>{li(s["points"])}</ul>
  {f'<p class="adv"><b>권하는 것</b> {esc(s["advice"])}</p>' if s["advice"] else ""}
  {f'<div class="tags">{tags}</div>' if tags else ""}
  <a class="go" href="{esc(v["url"])}" target="_blank" rel="noopener"><b>영상 보기 ›</b>
    <span>{v["published"][5:10].replace("-", ".")} · {esc(v["title"])}</span></a>
</article>''')

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
<meta name="theme-color" content="#FFFFFF" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#000000" media="(prefers-color-scheme: dark)">
<style>{TREND_CSS}</style>

<nav class="nav"><div class="in">
  <a class="logo" href="/">청약달력</a>
  <div class="links"><a href="/">청약 일정</a><a href="/jeonse">전세 가능 단지</a></div>
</div></nav>

<main>
  <section class="hero"><div class="in">
    <p class="eyebrow">부동산 유튜버 주간 요약</p>
    <h1>{esc(d["title"])}</h1>
    <p class="span">{span} · 채널 {channels}곳 · 영상 {len(videos)}편</p>
    <p class="lead">{esc(d["overview"])}</p>
  </div></section>

  <section class="band"><div class="in">
    <h2>이번 주, 집값을 어떻게 봤나</h2>
    <p class="sub">영상 {len(videos)}편이 앞으로의 집값을 어떻게 전망했는지 셌습니다.</p>
    <div class="stats">{stats}</div>
    <div class="meter">{meter}</div>

    <div class="cols">
      <div class="col"><h3>같은 방향으로 본 것</h3><ul>{li(d["consensus"])}</ul></div>
      <div class="col"><h3>의견이 갈린 것</h3><ul>{li(d["disagreements"])}</ul></div>
      <div class="col"><h3>자주 나온 이슈</h3><ul>{li(d["hot_topics"])}</ul></div>
    </div>
  </div></section>

  <section class="vids"><div class="in">
    <h2>영상별 요약</h2>
    <p class="sub">핵심만 세 줄로. 자세한 내용은 원본 영상에서.</p>
    <div class="grid">{"".join(cards)}</div>
  </div></section>
</main>

<footer class="foot"><div class="in">
  <p>이 요약은 AI가 영상을 보고 정리한 것으로, 출연자의 실제 발언과 다를 수 있습니다.
    정확한 내용은 원본 영상에서 확인하세요. 투자 권유가 아니며, 각 의견은 해당 출연자의 것입니다.</p>
  <p><a href="/">청약달력</a> · <a href="/privacy">개인정보처리방침</a> · <a href="/contact">문의하기</a></p>
</div></footer>
'''


def not_found_page(style):
    """없는 주소용. Cloudflare Pages 는 루트의 404.html 을 404 상태로 돌려준다.
    이 파일이 없으면 메인 페이지를 200 으로 내보내 구글이 soft 404 로 본다."""
    return f'''<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<html lang="ko">
<title>페이지를 찾을 수 없습니다 | 청약달력</title>
<meta name="robots" content="noindex">
{style}
<style>
.doc{{max-width:760px; margin:0 auto; padding:60px 16px}}
.doc h1{{font-family:"Noto Serif KR",serif; font-size:24px; margin:0 0 10px}}
.doc p{{color:var(--ink-2); font-size:14.5px; line-height:1.75}}
.doc a{{color:var(--accent)}}
</style>

<header>
  <div class="wrap hd">
    <a class="logo" href="/" style="text-decoration:none">청약<b>달력</b></a>
    <span class="tag">분양가 · 세대수 · 전매제한 · 실거주의무를 날짜순으로</span>
  </div>
</header>

<main class="doc">
  <h1>페이지를 찾을 수 없습니다</h1>
  <p>주소가 바뀌었거나 없는 페이지입니다.</p>
  <p><a href="/">전체 청약 일정 보기</a> · <a href="/jeonse">전세 가능 단지 보기</a></p>
</main>
'''


def main():
    src = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    style = re.search(r"<style>.*?</style>", src, re.S).group(0)

    data = json.load(open(os.path.join(ROOT, "data", "notices.json"), encoding="utf-8"))
    items = data["items"]
    updated = data.get("updated", str(date.today()))

    # 지난 공고 보관. 목록에서 빠진 날을 _closed 로 남긴다.
    archive = json.load(open(ARCHIVE, encoding="utf-8")) if os.path.exists(ARCHIVE) else {}
    current = {n["id"] for n in items}
    for n in items:
        archive[n["id"]] = n
    for k, n in archive.items():
        if k not in current and not n.get("_closed"):
            n["_closed"] = updated
    with open(ARCHIVE, "w", encoding="utf-8") as fp:
        json.dump({k: {f: v for f, v in n.items() if f != "_slug"} for k, n in archive.items()},
                  fp, ensure_ascii=False, indent=1)
    closed = sorted((n for k, n in archive.items() if k not in current),
                    key=lambda n: n["_closed"], reverse=True)

    os.makedirs(APT_DIR, exist_ok=True)
    keep = set()
    for n in items + closed:
        n["_slug"] = slug(n["name"], n["id"].split("-")[0])
        keep.add(n["_slug"] + ".html")
        with open(os.path.join(APT_DIR, n["_slug"] + ".html"), "w", encoding="utf-8") as fp:
            fp.write(page(n, style, updated))
    for f in os.listdir(APT_DIR):          # 단지명이 바뀌어 주소가 달라진 옛 파일만 정리
        if f.endswith(".html") and f not in keep:
            os.remove(os.path.join(APT_DIR, f))
    print(f"단지 페이지 {len(items)}개 + 마감 {len(closed)}개 생성", file=sys.stderr)

    with open(os.path.join(ROOT, "404.html"), "w", encoding="utf-8") as fp:
        fp.write(not_found_page(style))

    with open(os.path.join(ROOT, "jeonse.html"), "w", encoding="utf-8") as fp:
        fp.write(jeonse_page(items, style, updated))
    ok_n = sum(1 for n in items if n["live"] == 0)
    print(f"전세 가능 페이지 생성 (가능 {ok_n}곳)", file=sys.stderr)

    # 부동산 유튜버 주간 요약
    trends = []
    yt_videos = os.path.join(ROOT, "data", "yt", "videos.json")
    if os.path.exists(yt_videos):
        yv = json.load(open(yt_videos, encoding="utf-8"))
        os.makedirs(os.path.join(ROOT, "trend"), exist_ok=True)
        for p in sorted(glob.glob(os.path.join(ROOT, "data", "yt", "digest-*.json"))):
            d = json.load(open(p, encoding="utf-8"))
            vids = [yv[i] for i in d["videos"] if i in yv and yv[i].get("summary")]
            with open(os.path.join(ROOT, "trend", d["week"] + ".html"), "w", encoding="utf-8") as fp:
                fp.write(trend_page(d, vids, items + closed))
            trends.append(d)
        print(f"유튜버 주간 요약 {len(trends)}개 생성", file=sys.stderr)

    # 메인 아래쪽 정적 목록 (검색봇이 각 페이지를 찾아가는 통로)
    lis = "\n".join(
        f'<li><a href="/apt/{n["_slug"]}">{esc(n["name"])}</a>'
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
            (SITE + "/jeonse", updated, "daily", "0.9"),
            (SITE + "/privacy", updated, "yearly", "0.2"),
            (SITE + "/contact", updated, "yearly", "0.2")]
    urls += [(f"{SITE}/apt/{n['_slug']}", updated, "weekly", "0.8") for n in items]
    urls += [(f"{SITE}/apt/{n['_slug']}", n["_closed"], "monthly", "0.5") for n in closed]
    urls += [(f"{SITE}/trend/{d['week']}", d["made"][:10], "weekly", "0.7") for d in trends]
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
