import os
import re
import time
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
BASE = "https://www.googleapis.com/youtube/v3"
TOP_N = 30
REGION = os.environ.get("REGION_CODE", "KR")
# 쇼츠 판별 기준(초). 2024-10 이후 쇼츠는 최대 3분까지 가능
SHORTS_MAX_SEC = int(os.environ.get("SHORTS_MAX_SEC", "180"))
CACHE_TTL = int(os.environ.get("CACHE_TTL", "1800"))  # 30분

# main: 키워드 검색 시 함께 붙이는 대표어 / terms: 키워드 없이 볼 때 쓰는 OR 검색어
CATEGORIES = {
    "movie": {"label": "영화", "main": "영화", "terms": "영화", "category_id": "1"},
    "drama": {"label": "드라마", "main": "드라마", "terms": "드라마", "category_id": None},
    # 여행: 한국을 여행하는(외국인 포함) 영상만. 영어 영상도 나오도록 언어 제한을 해제(lang=None)
    "travel": {
        "label": "여행",
        "main": "Korea travel",
        "terms": "Korea travel|visit Korea|Korea trip|Seoul travel|Busan travel|Jeju travel|한국 여행|외국인 한국 여행",
        "category_id": "19",
        "lang": None,
    },
    "hallyu": {"label": "한류", "main": "한류", "terms": "한류|케이팝|K-pop|K-drama", "category_id": None},
}
DURATIONS = {"all": ["any"], "short": ["short"], "long": ["medium", "long"]}
PERIODS = {"all": None, "week": 7, "month": 30, "year": 365}

app = FastAPI(title="YouTube TOP 30")
_cache: dict = {}


def yt_get(path: str, params: dict) -> dict:
    if not API_KEY:
        raise HTTPException(500, "YOUTUBE_API_KEY 환경변수가 설정되지 않았습니다.")
    r = httpx.get(f"{BASE}/{path}", params={**params, "key": API_KEY}, timeout=15)
    if r.status_code != 200:
        reason = ""
        try:
            reason = r.json()["error"]["errors"][0]["reason"]
        except Exception:
            pass
        if reason in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"):
            raise HTTPException(429, "오늘의 YouTube API 쿼터를 모두 사용했습니다. 내일 다시 시도해 주세요.")
        raise HTTPException(502, f"YouTube API 오류({r.status_code}): {reason or r.text[:200]}")
    return r.json()


def iso_to_sec(d: str) -> int:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return 0
    days, h, mi, s = (int(x or 0) for x in m.groups())
    return days * 86400 + h * 3600 + mi * 60 + s


def search_ids(q: str, cat_id, duration: str, published_after, lang="ko") -> list:
    params = {
        "part": "id", "type": "video", "order": "viewCount", "maxResults": 50,
        "q": q, "regionCode": REGION, "videoDuration": duration,
    }
    if lang:
        params["relevanceLanguage"] = lang
    if cat_id:
        params["videoCategoryId"] = cat_id
    if published_after:
        params["publishedAfter"] = published_after
    data = yt_get("search", params)  # 100 유닛
    return [it["id"]["videoId"] for it in data.get("items", []) if it.get("id", {}).get("videoId")]


def fetch_details(ids: list) -> list:
    out = []
    for i in range(0, len(ids), 50):  # 호출당 1 유닛
        data = yt_get("videos", {"part": "snippet,contentDetails,statistics", "id": ",".join(ids[i:i + 50])})
        out.extend(data.get("items", []))
    return out


@app.get("/api/categories")
def categories():
    return [{"key": k, "label": v["label"]} for k, v in CATEGORIES.items()]


@app.get("/api/rank")
def rank(
    category: str = Query("movie"),
    q: str = Query("", max_length=80),
    format: str = Query("all"),
    period: str = Query("all"),
):
    if category not in CATEGORIES or format not in DURATIONS or period not in PERIODS:
        raise HTTPException(400, "잘못된 요청입니다.")
    cat = CATEGORIES[category]
    kw = q.strip()
    query = f"{kw} {cat['main']}" if kw else cat["terms"]

    key = (category, query, format, period)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return {**hit[1], "cached": True}

    after = None
    if PERIODS[period]:
        dt = datetime.now(timezone.utc) - timedelta(days=PERIODS[period])
        after = dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    ids: list = []
    for dur in DURATIONS[format]:
        for vid in search_ids(query, cat["category_id"], dur, after, cat.get("lang", "ko")):
            if vid not in ids:
                ids.append(vid)

    items = []
    for v in fetch_details(ids):
        sec = iso_to_sec(v["contentDetails"].get("duration"))
        is_short = 0 < sec <= SHORTS_MAX_SEC
        if format == "short" and not is_short:
            continue
        if format == "long" and is_short:
            continue
        st, sn = v.get("statistics", {}), v["snippet"]
        thumbs = sn.get("thumbnails", {})
        items.append({
            "id": v["id"],
            "title": sn["title"],
            "channel": sn["channelTitle"],
            "published": sn["publishedAt"][:10],
            "views": int(st.get("viewCount", 0)),
            "likes": int(st["likeCount"]) if "likeCount" in st else None,
            "duration": sec,
            "is_short": is_short,
            "thumb": (thumbs.get("medium") or thumbs.get("default") or {}).get("url", ""),
            "url": f"https://www.youtube.com/{'shorts/' if is_short else 'watch?v='}{v['id']}",
        })
    items.sort(key=lambda x: x["views"], reverse=True)
    items = items[:TOP_N]
    for i, it in enumerate(items, 1):
        it["rank"] = i

    result = {"query": query, "count": len(items), "items": items, "cached": False}
    if len(_cache) > 500:
        _cache.clear()
    _cache[key] = (time.time(), result)
    return result


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")
