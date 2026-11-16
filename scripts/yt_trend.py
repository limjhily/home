#!/usr/bin/env python3
"""
부동산 유튜버 주간 요약.

  1) data/yt_channels.json 의 채널마다 최근 영상 목록을 받는다 (YouTube Data API, 없으면 RSS)
  2) 제목·설명으로 부동산 영상만 고른다 (Gemini, 텍스트 한 번)
  3) 고른 영상을 Gemini 에 유튜브 링크째 넘겨 정해진 형식으로 요약한다
  4) 일주일치 요약을 모아 "이번 주 종합"을 만든다

결과는 data/yt/videos.json(영상별, 한 번 요약한 영상은 다시 부르지 않음)과
data/yt/digest-YYYY-Www.json(주간 종합)에 쌓인다.

GEMINI_API_KEY, YOUTUBE_API_KEY 는 환경변수 또는 저장소 루트의 .env 에서 읽는다.

무료 등급으로만 돌린다(결제를 연결하지 않은 프로젝트의 키). 무료 한도는 모델마다
분당 5회·하루 20회라서, 영상 요약은 하루 --max 편까지만 하고 나머지는 다음 날로 넘긴다.

  python3 scripts/yt_trend.py collect [--days 7] [--max 12]   # 매일
  python3 scripts/yt_trend.py digest  [--days 7]              # 매주
  python3 scripts/yt_trend.py prbody                          # 최신 주간 종합을 검토용 글로
"""
import argparse, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YT_DIR = os.path.join(ROOT, "data", "yt")
VIDEOS = os.path.join(YT_DIR, "videos.json")
# 앞 모델이 몰리거나(503) 하루 한도를 다 쓰면(429) 다음 모델로 넘어간다.
# 무료 한도(2026-11): Flash 는 모델마다 분당 5회·하루 20회, Flash-Lite 는 분당 15회·하루 500회.
VIDEO_MODELS = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3-flash-preview"]
TEXT_MODELS = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.8-flash"]
GAP = 13          # 같은 모델을 다시 부르기 전 간격(초). 분당 5회를 넘지 않게
MAX_FAILS = 3     # 이만큼 실패한 영상은 더 시도하지 않는다 (멤버십 전용·삭제 등)
KST = timezone(timedelta(hours=9))

NS = {"a": "http://www.w3.org/2005/Atom",
      "yt": "http://www.youtube.com/xml/schemas/2015",
      "media": "http://search.yahoo.com/mrss/"}


_last_call = {}


def gemini(parts, schema, models, tries=6):
    """JSON 으로 답을 받는다. 실패하면 None."""
    body = {"contents": [{"parts": parts}],
            "generationConfig": {"responseMimeType": "application/json",
                                 "responseSchema": schema, "temperature": 0.2}}
    if models is VIDEO_MODELS:   # 화면보다 말이 중요한 영상이라 낮은 해상도로 토큰을 아낀다
        body["generationConfig"]["mediaResolution"] = "MEDIA_RESOLUTION_LOW"
    for i in range(tries):
        model = models[i % len(models)]
        wait = GAP - (time.time() - _last_call.get(model, 0))
        if wait > 0:
            time.sleep(wait)
        _last_call[model] = time.time()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        req = urllib.request.Request(url, json.dumps(body).encode(), {
            "Content-Type": "application/json", "x-goog-api-key": env_key("GEMINI_API_KEY")})
        try:
            res = json.load(urllib.request.urlopen(req, timeout=600))
            return json.loads(res["candidates"][0]["content"]["parts"][0]["text"])
        except (OSError, KeyError, IndexError, json.JSONDecodeError) as e:   # 네트워크 끊김·시간 초과 포함
            msg = e.read().decode() if isinstance(e, urllib.error.HTTPError) else str(e)
            print(f"  Gemini 실패 {i+1}/{tries} ({model}): {' '.join(msg.split())[:200]}", file=sys.stderr)
    return None


def env_key(name):
    if os.environ.get(name):
        return os.environ[name]
    env = os.path.join(ROOT, ".env")
    if os.path.exists(env):
        for line in open(env, encoding="utf-8"):
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"')
    return ""


def yt_api(path, **params):
    params["key"] = env_key("YOUTUBE_API_KEY")
    url = f"https://www.googleapis.com/youtube/v3/{path}?" + urllib.parse.urlencode(params)
    return json.load(urllib.request.urlopen(url, timeout=30))


def duration_sec(iso):
    """PT1H2M3S → 초"""
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    d, h, mi, s = (int(x or 0) for x in m.groups()) if m else (0, 0, 0, 0)
    return d * 86400 + h * 3600 + mi * 60 + s


def recent_videos(ch, days):
    """채널의 최근 영상. YOUTUBE_API_KEY 가 있으면 공식 API(영상 길이 포함)를 쓰고,
    없으면 RSS 로 받는다. RSS 는 15개까지만 주고 이유 없이 404 를 낼 때가 많다."""
    if not env_key("YOUTUBE_API_KEY"):
        return recent_videos_rss(ch, days)
    cut = datetime.now(timezone.utc) - timedelta(days=days)
    try:   # 업로드 재생목록 ID 는 채널 ID 의 UC 를 UU 로 바꾼 것
        items, token = [], ""
        for _ in range(4):   # 하루 여러 편 올리는 채널은 일주일에 50편을 넘는다
            r = yt_api("playlistItems", part="snippet,contentDetails", maxResults=50,
                       playlistId="UU" + ch["id"][2:], **({"pageToken": token} if token else {}))
            items += r["items"]
            token = r.get("nextPageToken")
            last = items[-1]["contentDetails"].get("videoPublishedAt", "") if items else ""
            if not token or last < cut.strftime("%Y-%m-%dT%H:%M:%SZ"):
                break
        out = []
        for it in items:
            pub = datetime.fromisoformat(it["contentDetails"]["videoPublishedAt"].replace("Z", "+00:00"))
            if pub < cut:
                continue
            vid = it["contentDetails"]["videoId"]
            out.append({"id": vid, "channel": ch["name"], "title": it["snippet"]["title"],
                        "published": pub.astimezone(KST).isoformat(timespec="minutes"),
                        "url": f"https://www.youtube.com/watch?v={vid}",
                        "description": it["snippet"].get("description", "")[:300]})
        info = {}
        for i in range(0, len(out), 50):   # 한 번에 50개까지만 받는다
            det = yt_api("videos", part="contentDetails,snippet", id=",".join(v["id"] for v in out[i:i + 50]))
            info.update({d["id"]: d for d in det["items"]})
        for v in out:
                d = info.get(v["id"], {})
                v["seconds"] = duration_sec(d.get("contentDetails", {}).get("duration"))
                v["live"] = d.get("snippet", {}).get("liveBroadcastContent", "none")
        return out
    except (OSError, KeyError, ValueError) as e:
        print(f"{ch['name']}: YouTube API 실패({e}), RSS 로 시도", file=sys.stderr)
        return recent_videos_rss(ch, days)


def recent_videos_rss(ch, days):
    req = urllib.request.Request(
        f"https://www.youtube.com/feeds/videos.xml?channel_id={ch['id']}",
        headers={"User-Agent": "Mozilla/5.0"})
    for i in range(4):   # RSS 는 가끔 이유 없이 404 를 낸다
        try:
            root = ET.fromstring(urllib.request.urlopen(req, timeout=30).read())
            break
        except (OSError, ET.ParseError):
            time.sleep(3 * (i + 1))
    else:
        print(f"{ch['name']}: RSS 를 받지 못해 건너뜀", file=sys.stderr)
        return []
    cut = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for e in root.findall("a:entry", NS):
        pub = datetime.fromisoformat(e.find("a:published", NS).text)
        if pub < cut:
            continue
        vid = e.find("yt:videoId", NS).text
        desc = e.find("media:group/media:description", NS)
        out.append({"id": vid, "channel": ch["name"], "title": e.find("a:title", NS).text,
                    "published": pub.astimezone(KST).isoformat(timespec="minutes"),
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "description": (desc.text or "")[:300] if desc is not None else ""})
    return out


CLASSIFY_SCHEMA = {"type": "array", "items": {"type": "object", "properties": {
    "id": {"type": "string"},
    "topic": {"type": "string", "enum": ["부동산", "주식·경제", "기타"]}},
    "required": ["id", "topic"]}}

CLASSIFY_PROMPT = """아래는 한국 재테크 유튜브 채널의 영상 제목과 설명이다.
각 영상의 주제를 하나로 분류하라.
- 부동산: 아파트·주택 시장, 집값 전망, 청약·분양, 전월세, 재건축·재개발, 부동산 정책·대출·세금
- 주식·경제: 주식, 코스피, 반도체, 미국 증시, 금리·환율 같은 거시경제 일반
- 기타: 노후·연금, 소비 습관, 직장 생활 등 그 밖의 것
금리·경제 이야기가 섞여 있어도 결론이 집값이나 내 집 마련이면 부동산이다.
"""


def classify(videos):
    lines = "\n".join(f"{v['id']}\t[{v['channel']}] {v['title']}\t{v['description'][:150].replace(chr(10), ' ')}"
                      for v in videos)
    res = gemini([{"text": CLASSIFY_PROMPT + "\n" + lines}], CLASSIFY_SCHEMA, TEXT_MODELS) or []
    return {r["id"]: r["topic"] for r in res}


SUMMARY_SCHEMA = {"type": "object", "properties": {
    "speaker": {"type": "string", "description": "주로 말하는 사람 (채널 진행자 또는 게스트, 직함 포함)"},
    "outlook": {"type": "string", "enum": ["상승", "보합", "하락", "혼조", "판단 없음"],
                "description": "이 영상이 앞으로의 집값을 어떻게 보는지"},
    "outlook_scope": {"type": "string", "description": "전망 대상 (예: 서울 아파트, 수도권 전세, 전국)"},
    "headline": {"type": "string", "description": "영상의 요지 한 문장"},
    "points": {"type": "array", "items": {"type": "string"},
               "description": "핵심 주장 3개. 각각 근거 포함 한두 문장"},
    "regions": {"type": "array", "items": {"type": "string"}, "description": "구체적으로 언급한 지역"},
    "complexes": {"type": "array", "items": {"type": "string"}, "description": "언급한 아파트 단지명"},
    "keywords": {"type": "array", "items": {"type": "string"}, "description": "정책·이슈 키워드 3~5개"},
    "advice": {"type": "string", "description": "시청자에게 권하는 행동 (없으면 빈 문자열)"}},
    "required": ["speaker", "outlook", "outlook_scope", "headline", "points",
                 "regions", "complexes", "keywords", "advice"]}

SUMMARY_PROMPT = """이 부동산 유튜브 영상을 보고 내용을 정리하라.
- 영상에서 실제로 말한 내용만 쓴다. 추측하거나 덧붙이지 않는다.
- 출연자의 의견은 출연자의 의견으로 쓴다 ("~라고 본다", "~라고 주장한다").
- 숫자(가격, 비율, 날짜)는 말한 그대로 옮긴다.
- 한국어, 짧고 담백한 문장.
영상 제목: {title}
"""


def summarize(v):
    # 말이 중심인 영상이라 5초에 한 장만 본다. 무료 한도(분당 25만 토큰)에 1시간 넘는 영상도 들어간다.
    return gemini([{"text": SUMMARY_PROMPT.format(title=v["title"])},
                   {"file_data": {"file_uri": v["url"], "mime_type": "video/*"},
                    "video_metadata": {"fps": 0.2}}],
                  SUMMARY_SCHEMA, VIDEO_MODELS, tries=3)


def load_videos():
    return json.load(open(VIDEOS, encoding="utf-8")) if os.path.exists(VIDEOS) else {}


def save_videos(db):
    os.makedirs(YT_DIR, exist_ok=True)
    with open(VIDEOS, "w", encoding="utf-8") as fp:
        json.dump(db, fp, ensure_ascii=False, indent=1)


def collect(days, max_n):
    if not env_key("GEMINI_API_KEY"):
        sys.exit("GEMINI_API_KEY 가 없습니다 (.env 또는 환경변수)")
    channels = json.load(open(os.path.join(ROOT, "data", "yt_channels.json"), encoding="utf-8"))
    db = load_videos()

    # 1) 새 영상을 모아 한 번에 분류한다 (하루 요청 수를 아끼려고 채널별로 나누지 않는다)
    new = []
    for ch in channels:
        vids = [v for v in recent_videos(ch, days) if v["id"] not in db]
        print(f"{ch['name']}: 새 영상 {len(vids)}개", file=sys.stderr)
        new += vids
    if new:
        # 쇼츠(3분 미만)와 아직 끝나지 않은 라이브는 분류할 것도 없이 뺀다
        skip = [v for v in new if 0 < v.get("seconds", 999) < 180 or v.get("live", "none") != "none"]
        new = [v for v in new if v not in skip]
        for v in skip:
            if v.get("live", "none") == "none":   # 라이브는 끝난 뒤 다시 보도록 저장하지 않는다
                v["topic"] = "쇼츠"
                del v["description"]
                db[v["id"]] = v
        topics = classify(new) if new else {}
        if topics or not new:
            for v in new:
                v["topic"] = topics.get(v["id"], "기타")
                v.pop("live", None)
                del v["description"]
                db[v["id"]] = v
            save_videos(db)
        else:   # 저장하지 않으면 다음 실행 때 다시 분류한다
            print("분류 실패, 다음 실행으로 넘김", file=sys.stderr)

    # 2) 아직 요약하지 않은 부동산 영상을 최신순으로 max_n 편까지
    cut = (datetime.now(KST) - timedelta(days=days + 1)).isoformat()
    todo = [v for v in db.values() if v["topic"] == "부동산" and not v.get("summary")
            and v.get("fails", 0) < MAX_FAILS and v["published"] >= cut]
    todo.sort(key=lambda v: v["published"], reverse=True)
    print(f"요약 대기 {len(todo)}편 중 {min(len(todo), max_n)}편 처리", file=sys.stderr)
    ok = 0
    for v in todo[:max_n]:
        print(f"  요약: [{v['channel']}] {v['title'][:40]}", file=sys.stderr)
        s = summarize(v)
        if s:
            v["summary"] = s
            v.pop("fails", None)
            ok += 1
        else:
            v["fails"] = v.get("fails", 0) + 1
        save_videos(db)   # 중간에 끊겨도 한 일은 남긴다
    print(f"요약 성공 {ok}편", file=sys.stderr)


DIGEST_SCHEMA = {"type": "object", "properties": {
    "title": {"type": "string", "description": "이번 주를 한 줄로 (기사 제목처럼)"},
    "overview": {"type": "string", "description": "이번 주 유튜버들의 시장 시각 종합, 3~4문장"},
    "consensus": {"type": "array", "items": {"type": "string"}, "description": "대부분이 같은 방향으로 본 것"},
    "disagreements": {"type": "array", "items": {"type": "string"}, "description": "의견이 갈린 지점 (누가 어떻게)"},
    "hot_topics": {"type": "array", "items": {"type": "string"}, "description": "자주 나온 이슈 3~5개"}},
    "required": ["title", "overview", "consensus", "disagreements", "hot_topics"]}

DIGEST_PROMPT = """아래는 이번 주 한국 부동산 유튜브 영상들의 요약이다.
여러 유튜버의 시각을 종합해 이번 주 부동산 시장 분위기를 정리하라.
- 요약에 있는 내용만 쓴다. 누가 말했는지 채널명이나 출연자로 밝힌다.
- 투자 권유가 아니라 "유튜버들이 이렇게 보고 있다"를 전하는 글이다.
"""


def digest(days):
    db = load_videos()
    cut = (datetime.now(KST) - timedelta(days=days)).isoformat()
    vids = [v for v in db.values() if v.get("summary") and v["published"] >= cut]
    vids.sort(key=lambda v: v["published"], reverse=True)
    text = "\n\n".join(f"[{v['channel']}] {v['title']}\n" + json.dumps(v["summary"], ensure_ascii=False)
                       for v in vids)
    if len(vids) < 3:
        sys.exit(f"요약된 영상이 {len(vids)}편뿐이라 주간 종합을 만들지 않습니다")
    d = gemini([{"text": DIGEST_PROMPT + "\n" + text}], DIGEST_SCHEMA, TEXT_MODELS[::-1])
    if not d:
        sys.exit("주간 종합 실패")
    cnt = {}
    for v in vids:
        cnt[v["summary"]["outlook"]] = cnt.get(v["summary"]["outlook"], 0) + 1
    # 월요일 새벽에 지난 7일을 정리하므로, 주차는 어제(일요일)가 속한 주로 붙인다
    y, w, _ = (datetime.now(KST) - timedelta(days=1)).isocalendar()
    d.update({"week": f"{y}-W{w:02d}", "made": datetime.now(KST).isoformat(timespec="minutes"),
              "outlook_count": cnt, "videos": [v["id"] for v in vids]})
    path = os.path.join(YT_DIR, f"digest-{y}-W{w:02d}.json")
    json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"주간 종합 저장: {path} (영상 {len(vids)}개)", file=sys.stderr)


def prbody():
    """최신 주간 종합을 사람이 읽기 좋은 글로. 검토 요청(PR) 본문에 쓴다."""
    import glob
    paths = sorted(glob.glob(os.path.join(YT_DIR, "digest-*.json")))
    if not paths:
        sys.exit("주간 종합이 없습니다")
    d = json.load(open(paths[-1], encoding="utf-8"))
    db = load_videos()
    out = [f"# {d['title']}", "", d["overview"], "",
           "**전망 분포** " + " · ".join(f"{k} {n}" for k, n in d["outlook_count"].items()), ""]
    for h, k in [("같은 방향으로 본 것", "consensus"), ("의견이 갈린 것", "disagreements"),
                 ("자주 나온 이슈", "hot_topics")]:
        out += [f"## {h}"] + [f"- {x}" for x in d[k]] + [""]
    out += [f"## 영상별 요약 ({len(d['videos'])}편)", ""]
    for vid in d["videos"]:
        v = db[vid]
        s = v["summary"]
        out += [f"### [{v['channel']}] {s['headline']}",
                f"{s['speaker']} · 전망 **{s['outlook']}** · [원본 영상]({v['url']})"]
        out += [f"- {x}" for x in s["points"]] + [""]
    out += ["---", "내용이 괜찮으면 **Merge** 를 누르세요. 사이트에 "
            f"`/trend/{d['week']}` 페이지로 게시됩니다. 틀린 요약이 있으면 "
            f"`data/yt/digest-{d['week']}.json` 의 `videos` 에서 그 영상 ID 를 지우면 빠집니다."]
    print("\n".join(out))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["collect", "digest", "prbody"])
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--max", type=int, default=12, help="한 번에 요약할 최대 영상 수")
    a = ap.parse_args()
    {"collect": lambda: collect(a.days, a.max), "digest": lambda: digest(a.days), "prbody": prbody}[a.cmd]()
