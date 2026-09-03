#!/usr/bin/env python3
"""
청약홈 분양정보 수집기

공공데이터포털(data.go.kr)의 "한국부동산원_청약홈 분양정보 조회 서비스"에서
APT 분양 공고와 주택형별 공급 정보를 받아 사이트가 읽는 data/notices.json 을 만든다.

사용법
  export DATA_GO_KR_KEY="발급받은 디코딩 서비스키"
  python3 scripts/collect.py                 # 최근 30일 ~ 앞으로 90일 공고 수집
  python3 scripts/collect.py --days-back 60
  python3 scripts/collect.py --selftest      # 키 없이 변환 로직만 검증
  python3 scripts/collect.py --debug         # 응답의 실제 필드명 출력

주의
  전매제한 기간과 실거주의무는 이 API에 들어있지 않다.
  data/overrides.json 에 단지별로 손으로 적어두면 그 값이 합쳐진다.
  값이 없으면 사이트에 "확인 필요"로 표시된다.
"""
import argparse, json, os, re, sys, time
from datetime import date, timedelta
from urllib import request, parse, error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE = "https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1"
LIST_OP = "getAPTLttotPblancDetail"   # 공고 목록
MODEL_OP = "getAPTLttotPblancMdl"     # 주택형별 공급/분양가
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fetch(op, params, key, retries=3):
    q = dict(params); q["serviceKey"] = key
    url = f"{BASE}/{op}?" + parse.urlencode(q, safe="[]:")
    for i in range(retries):
        try:
            with request.urlopen(url, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and i < retries - 1:
                time.sleep(2 ** i); continue
            raise SystemExit(f"[에러] {op} HTTP {e.code}: {e.read()[:300].decode('utf-8','replace')}")
        except Exception as e:
            if i < retries - 1:
                time.sleep(2 ** i); continue
            raise SystemExit(f"[에러] {op}: {e}")


def d(v):
    """20260907 / 2026-09-07 / 2026.09.07 → 2026-09-07"""
    if not v: return None
    s = re.sub(r"[^0-9]", "", str(v))
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 else None


def i(v, default=0):
    try: return int(re.sub(r"[^0-9-]", "", str(v)) or default)
    except Exception: return default


def f(v, default=0.0):
    try: return float(re.sub(r"[^0-9.]", "", str(v)) or default)
    except Exception: return default


def zone_of(r):
    if str(r.get("SPECLT_RDN_EARTH_AT", "")).upper().startswith("Y"): return "투기과열지구"
    if str(r.get("MDAT_TRGET_AREA_SECD", "")).upper().startswith("Y"): return "조정대상지역"
    return "비규제지역"


def kind_of(r):
    s = (r.get("HOUSE_DTL_SECD_NM") or r.get("HOUSE_SECD_NM") or "").strip()
    if "국민" in s or "공공" in s: return "공공"
    return "민영"


def district_of(addr, region):
    """'경기도 성남시 수정구 …' → '성남시 수정구'"""
    if not addr: return ""
    parts = addr.split()
    body = [p for p in parts[1:] if p.endswith(("시", "군", "구", "동", "읍", "면"))]
    return " ".join(body[:2])


def build(rec, models):
    units = []
    for m in models:
        # SUPLY_HSHLDCO 는 '일반공급' 세대수, SPSPLY_HSHLDCO 는 '특별공급' 세대수다.
        # (데이터 검증 결과: 총세대 = 일반 + 특별)
        gen = i(m.get("SUPLY_HSHLDCO"))
        sp = i(m.get("SPSPLY_HSHLDCO"))
        units.append({
            "t": (m.get("HOUSE_TY") or "").strip(),
            "area": round(f(m.get("SUPLY_AR")), 2),
            "n": gen + sp,      # 타입별 총 세대수
            "gen": gen,         # 그중 일반공급
            "price": i(m.get("LTTOT_TOP_AMOUNT")),
        })
    units = [u for u in units if u["area"] > 0 and u["price"] > 0]
    if not units:
        return None  # 분양가 없는 공고는 표시할 게 없으므로 제외

    total = i(rec.get("TOT_SUPLY_HSHLDCO")) or sum(u["n"] for u in units)
    general = sum(u["gen"] for u in units)
    region = (rec.get("SUBSCRPT_AREA_CODE_NM") or "").strip()
    addr = (rec.get("HSSPLY_ADRES") or "").strip()

    notes = []
    if str(rec.get("PARCPRC_ULS_AT", "")).upper().startswith("Y"):
        notes.append("분양가상한제 적용 단지")
    if str(rec.get("PUBLIC_HOUSE_EARTH_AT", "")).upper().startswith("Y"):
        notes.append("공공택지")
    if rec.get("BSNS_MBY_NM"):
        notes.append(f"시행사 {rec['BSNS_MBY_NM']}")

    c1, c2 = d(rec.get("CNTRCT_CNCLS_BGNDE")), d(rec.get("CNTRCT_CNCLS_ENDDE"))
    return {
        "id": f"{rec.get('HOUSE_MANAGE_NO')}-{rec.get('PBLANC_NO')}",
        "name": (rec.get("HOUSE_NM") or "").strip(),
        "region": region,
        "district": district_of(addr, region),
        "type": kind_of(rec),
        "total": total,
        "general": general,
        "builder": (rec.get("CNSTRCT_ENTRPS_NM") or "").strip(),
        "zone": zone_of(rec),
        "special": d(rec.get("SPSPLY_RCEPT_BGNDE")) or d(rec.get("RCEPT_BGNDE")),
        "first": d(rec.get("GNRL_RNK1_CRSPAREA_RCPTDE")) or d(rec.get("GNRL_RNK1_CRSPAREA_RCEPT_PD")),
        "second": d(rec.get("GNRL_RNK2_CRSPAREA_RCPTDE")) or d(rec.get("GNRL_RNK2_CRSPAREA_RCEPT_PD")),
        "result": d(rec.get("PRZWNER_PRESNATN_DE")),
        "contract": f"{c1} ~ {c2[5:]}" if c1 and c2 else (c1 or ""),
        "resale": None,   # API 미제공 → overrides.json 에서 보정
        "live": None,     # API 미제공 → overrides.json 에서 보정
        "link": rec.get("PBLANC_URL") or "https://www.applyhome.co.kr",
        "units": sorted(units, key=lambda u: u["area"]),
        "notes": notes,
    }


def enrich_from_pdf(items, force=False):
    """각 공고의 상세 페이지에서 공고문 PDF를 찾아 전매제한·거주의무를 채운다.

    실패하면 조용히 넘어간다(값은 None 으로 남고 사이트에 '확인 필요'로 표시).
    한 번 읽은 공고는 data/pdf_cache.json 에 저장해 다음 실행에서 건너뛴다.
    """
    try:
        import pblanc_pdf
        from probe_applyhome import get, find_links
    except Exception as e:
        print(f"[PDF] 모듈 없음, 건너뜀: {e}", file=sys.stderr)
        return items

    cache_path = os.path.join(ROOT, "data", "pdf_cache.json")
    cache = {}
    if os.path.exists(cache_path) and not force:
        try: cache = json.load(open(cache_path, encoding="utf-8"))
        except Exception: pass

    tmp = os.path.join(ROOT, "_pblanc.pdf")
    hit = cached = fail = 0
    for it in items:
        key = it["id"]
        if key in cache:
            it.update(cache[key]); cached += 1; continue
        got = None
        try:
            _, _, body = get(it["link"])
            html = body.decode("utf-8", "replace")
            for u in find_links(html, it["link"]):
                if not any(k in u.lower() for k in ("pdf", "download", "file", "atch")):
                    continue
                try:
                    _, ct, blob = get(u, referer=it["link"])
                except Exception:
                    continue
                if blob[:5] != b"%PDF-" and "pdf" not in ct.lower():
                    continue
                with open(tmp, "wb") as fp: fp.write(blob)
                got = pblanc_pdf.parse_pdf(tmp)
                break
        except Exception as e:
            print(f"[PDF] {it['name'][:20]}: {e}", file=sys.stderr)

        if got and (got["resale"] is not None or got["live"] is not None):
            it.update(got); cache[key] = got; hit += 1
        else:
            fail += 1
    if os.path.exists(tmp): os.remove(tmp)

    with open(cache_path, "w", encoding="utf-8") as fp:
        json.dump(cache, fp, ensure_ascii=False, indent=1)
    print(f"[PDF] 추출 성공 {hit} · 캐시 {cached} · 실패 {fail}", file=sys.stderr)
    return items


def apply_overrides(items):
    path = os.path.join(ROOT, "data", "overrides.json")
    if not os.path.exists(path): return items
    ov = json.load(open(path, encoding="utf-8"))
    for it in items:
        for key in (it["id"], it["name"]):
            if key in ov:
                it.update(ov[key]); break
    return items


def collect(key, days_back, days_fwd, debug):
    today = date.today()
    since = (today - timedelta(days=days_back)).strftime("%Y-%m-%d")
    until = (today + timedelta(days=days_fwd)).strftime("%Y-%m-%d")

    rows, page = [], 1
    while True:
        res = fetch(LIST_OP, {
            "page": page, "perPage": 100,
            "cond[RCRIT_PBLANC_DE::GTE]": since,
            "cond[RCRIT_PBLANC_DE::LTE]": until,
        }, key)
        data = res.get("data", [])
        if debug and page == 1 and data:
            print("[디버그] 공고 응답 필드:", ", ".join(sorted(data[0].keys())), file=sys.stderr)
        rows += data
        if len(data) < 100: break
        page += 1
    print(f"공고 {len(rows)}건 조회 ({since} ~ {until})", file=sys.stderr)

    items = []
    for n, rec in enumerate(rows, 1):
        res = fetch(MODEL_OP, {
            "page": 1, "perPage": 100,
            "cond[HOUSE_MANAGE_NO::EQ]": rec.get("HOUSE_MANAGE_NO"),
            "cond[PBLANC_NO::EQ]": rec.get("PBLANC_NO"),
        }, key)
        models = res.get("data", [])
        if debug and n == 1 and models:
            print("[디버그] 주택형 응답 필드:", ", ".join(sorted(models[0].keys())), file=sys.stderr)
        built = build(rec, models)
        if built and built["special"]:
            items.append(built)
        time.sleep(0.1)  # 호출 간격
    return items


def save(items, use_pdf=True, force_pdf=False):
    if use_pdf:
        items = enrich_from_pdf(items, force_pdf)
    items = apply_overrides(items)   # 수동 보정이 항상 우선
    items.sort(key=lambda x: x["special"])
    out = {"updated": date.today().strftime("%Y-%m-%d"), "count": len(items), "items": items}
    path = os.path.join(ROOT, "data", "notices.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=1)
    print(f"저장 완료: data/notices.json ({len(items)}건)", file=sys.stderr)
    return out


FIXTURE_REC = {
    "HOUSE_MANAGE_NO": "2026000123", "PBLANC_NO": "2026000123",
    "HOUSE_NM": "○○지구 테스트아파트", "SUBSCRPT_AREA_CODE_NM": "경기",
    "HSSPLY_ADRES": "경기도 성남시 수정구 창곡동 123", "HOUSE_DTL_SECD_NM": "민영주택",
    "TOT_SUPLY_HSHLDCO": "770", "CNSTRCT_ENTRPS_NM": "테스트건설",
    "SPECLT_RDN_EARTH_AT": "N", "MDAT_TRGET_AREA_SECD": "Y", "PARCPRC_ULS_AT": "Y",
    "BSNS_MBY_NM": "테스트개발", "SPSPLY_RCEPT_BGNDE": "20260907",
    "GNRL_RNK1_CRSPAREA_RCPTDE": "20260908", "GNRL_RNK2_CRSPAREA_RCPTDE": "20260909",
    "PRZWNER_PRESNATN_DE": "20260916", "CNTRCT_CNCLS_BGNDE": "20260928",
    "CNTRCT_CNCLS_ENDDE": "20260930", "PBLANC_URL": "https://www.applyhome.co.kr",
}
FIXTURE_MDL = [
    {"HOUSE_TY": "059.9400A", "SUPLY_AR": "59.94", "SUPLY_HSHLDCO": "200", "SPSPLY_HSHLDCO": "110", "LTTOT_TOP_AMOUNT": "78400"},
    {"HOUSE_TY": "084.9600A", "SUPLY_AR": "84.96", "SUPLY_HSHLDCO": "300", "SPSPLY_HSHLDCO": "160", "LTTOT_TOP_AMOUNT": "106500"},
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days-back", type=int, default=30)
    ap.add_argument("--days-forward", type=int, default=90)
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--selftest", action="store_true", help="키 없이 변환 로직만 검증")
    ap.add_argument("--no-pdf", action="store_true", help="공고문 PDF 추출 건너뛰기")
    ap.add_argument("--force-pdf", action="store_true", help="PDF 캐시 무시하고 다시 읽기")
    a = ap.parse_args()

    if a.selftest:
        item = build(FIXTURE_REC, FIXTURE_MDL)
        assert item and item["special"] == "2026-09-07", item
        assert item["total"] == 770 and item["general"] == 500, item
        assert item["units"][0]["n"] == 310 and item["units"][0]["gen"] == 200, item
        assert item["zone"] == "조정대상지역" and item["type"] == "민영", item
        assert item["district"] == "성남시 수정구", item
        assert len(item["units"]) == 2 and item["units"][0]["price"] == 78400, item
        print(json.dumps(item, ensure_ascii=False, indent=1))
        print("\n[selftest] 통과", file=sys.stderr)
        return

    key = os.environ.get("DATA_GO_KR_KEY")
    if not key:
        raise SystemExit("DATA_GO_KR_KEY 환경변수가 필요합니다. data.go.kr에서 서비스키를 발급받으세요.")
    save(collect(key, a.days_back, a.days_forward, a.debug),
         use_pdf=not a.no_pdf, force_pdf=a.force_pdf)


if __name__ == "__main__":
    main()
