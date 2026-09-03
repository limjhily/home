#!/usr/bin/env python3
"""
입주자모집공고문 PDF에서 전매제한 기간과 거주의무(실거주의무) 기간을 뽑아낸다.

청약홈 OpenAPI에는 이 두 항목이 없어서, 공고문 원문에서 직접 읽는다.

핵심 로직인 parse_text() 는 문자열만 받는 순수 함수라 PDF 없이도 검증할 수 있다.
  python3 scripts/pblanc_pdf.py --selftest
"""
import argparse, json, os, re, sys

# ── 기간 표기 정규화 ────────────────────────────────────────────────
_NUM = {"영":0,"일":1,"이":2,"삼":3,"사":4,"오":5,"육":6,"칠":7,"팔":8,"구":9,"십":10}

def _to_months(value, unit):
    n = int(value)
    return n * 12 if unit == "년" else n

# 값이 "없음"이라고 적힌 경우를 잡는 표현들
_NONE_WORDS = r"(?:해당\s*(?:사항)?\s*없음|해당없음|없음|미적용|적용\s*제외|해당\s*무)"

# 숫자 + 단위. "3년", "36개월", "1년 6개월" 형태를 모두 잡는다.
_PERIOD = r"(\d{1,3})\s*(년|개월|월)"

def _scan(text, labels, window=120):
    """라벨 뒤 window 글자 안에서 기간 또는 '없음'을 찾아 후보 목록을 만든다."""
    out = []
    for label in labels:
        for m in re.finditer(label, text):
            seg = text[m.end(): m.end() + window]
            seg = seg.split("\n\n")[0]          # 문단을 넘어가지 않도록
            none_hit = re.search(_NONE_WORDS, seg)
            per_hit = re.search(_PERIOD, seg)
            if none_hit and (not per_hit or none_hit.start() < per_hit.start()):
                out.append(0)
                continue
            if per_hit:
                months = _to_months(per_hit.group(1), per_hit.group(2))
                # "1년 6개월" 처럼 뒤에 덧붙는 경우
                tail = re.match(r"\s*(\d{1,2})\s*(개월|월)", seg[per_hit.end():])
                if tail and per_hit.group(2) == "년":
                    months += int(tail.group(1))
                out.append(months)
    return out


def _pick(cands):
    """후보 중 가장 많이 나온 값. 동률이면 먼저 나온 값."""
    if not cands: return None
    best, seen = None, {}
    for c in cands:
        seen[c] = seen.get(c, 0) + 1
    top = max(seen.values())
    for c in cands:
        if seen[c] == top:
            best = c; break
    return best


RESALE_LABELS = [
    r"전매\s*행위\s*제한\s*기간", r"전매\s*제한\s*기간", r"전매\s*행위\s*제한",
    r"전매\s*제한", r"전매\s*행위의?\s*제한",
]
LIVE_LABELS = [
    r"거주\s*의무\s*기간", r"실\s*거주\s*의무\s*기간", r"의무\s*거주\s*기간",
    r"거주\s*의무", r"실\s*거주\s*의무",
]


def parse_text(text):
    """공고문 전체 텍스트 → {"resale": 개월수|None, "live": 연수|None}"""
    text = re.sub(r"[ \t ]+", " ", text)
    resale = _pick(_scan(text, RESALE_LABELS))
    live_m = _pick(_scan(text, LIVE_LABELS))
    live = None if live_m is None else (0 if live_m == 0 else round(live_m / 12))
    return {"resale": resale, "live": live}


# ── PDF 읽기 ────────────────────────────────────────────────────────
def pdf_text(path, max_pages=25):
    """앞쪽 페이지에 주요 안내사항이 몰려 있어 기본 25쪽만 읽는다."""
    import pdfplumber
    parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages[:max_pages]:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def parse_pdf(path, max_pages=25):
    return parse_text(pdf_text(path, max_pages))


# ── 자체 검증 ───────────────────────────────────────────────────────
CASES = [
    ("전매행위 제한기간 : 당첨자발표일로부터 3년\n거주의무기간 : 3년",
     {"resale": 36, "live": 3}),
    ("○ 전매제한기간: 6개월\n○ 거주의무기간: 해당사항 없음",
     {"resale": 6, "live": 0}),
    ("본 주택은 「주택법」 제64조에 따라 당첨자발표일부터 전매제한 1년이 적용됩니다.\n"
     "「주택법」 제57조의2에 따른 거주의무는 해당없음",
     {"resale": 12, "live": 0}),
    ("전매 행위 제한 기간 36개월\n실거주의무기간 2년",
     {"resale": 36, "live": 2}),
    ("전매제한기간 : 없음\n의무거주기간 : 5년",
     {"resale": 0, "live": 5}),
    ("전매제한기간은 1년 6개월입니다.",
     {"resale": 18, "live": None}),
    ("본 공고문에는 관련 문구가 없습니다.",
     {"resale": None, "live": None}),
    # 같은 값이 여러 번 반복되는 실제 공고문 형태
    ("전매제한기간 3년\n...중략...\n전매행위 제한기간은 3년이며\n거주의무기간 3년 적용",
     {"resale": 36, "live": 3}),
]


def selftest():
    ok = True
    for i, (text, want) in enumerate(CASES, 1):
        got = parse_text(text)
        mark = "OK " if got == want else "실패"
        if got != want: ok = False
        print(f"[{mark}] {i}. {text.splitlines()[0][:38]:40} → {got}")
    print("\n[selftest] " + ("통과" if ok else "실패"), file=sys.stderr)
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", nargs="?", help="공고문 PDF 경로")
    ap.add_argument("--pages", type=int, default=25)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest: sys.exit(selftest())
    if not a.pdf: ap.error("PDF 경로가 필요합니다 (또는 --selftest)")
    print(json.dumps(parse_pdf(a.pdf, a.pages), ensure_ascii=False))


if __name__ == "__main__":
    main()
