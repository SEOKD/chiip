"""YouTube 공식 IR 채널 새 영상(결산 설명회) 탐지 — 공식 YouTube Data API v3, 메타데이터만 (마스터 지시 2026-11-09 JX금속 "결산 동영상을 보고 텍스트를 추출해 어닝콜 스크립트를 뽑아 분석하는 구조").

경계(2026-11-09 확인): YouTube는 약관상 영상 내려받기 금지이고 robots.txt가 /timedtext_video(자막)·/get_video_info·/feeds/videos.xml(RSS)·/youtubei/를 막는다.
→ 영상·음성·자막에서 직접 텍스트를 뽑지 않는다(radar/ir_audio.py도 YouTube 제외). 공식 API로 '게시'만 즉시 잡는다.
내용 분석은 허용 경로로: ① TradingView 문서(Quartr) 어닝콜 전사·Q&A — radar/jp_tv_docs.py가 결산 후 6~72시간 간격으로 다시 본다
② 회사 사이트의 質疑応答要旨·書き起こし(jp_ir_qa) ③ 회사가 같은 설명회를 자체 사이트·IR 대행 재생기(video-streaming.net 등)에 올리면 ir_audio가 전사
④ 셋 다 없으면 PT·결산단신·Quartr 슬라이드 요약으로 분석하고 '설명회 원문 미확보'를 적는다. 기자 경로(회사 IR에 음성·전사 요청)는 마스터 몫.
키: YOUTUBE_API_KEY(무료, Google Cloud 콘솔 'YouTube Data API v3' 사용 설정 후 API 키) — 없으면 '키 대기'로 건너뛴다(docs/TODO_MASTER.md 21-40).
쿼터: 채널당 playlistItems 1단위/회. 채널 id 확인(forHandle·search)은 처음 한 번만.
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pollers import common  # noqa: E402

SRC = "src-yt-ir"
API = "https://www.googleapis.com/youtube/v3/"
RESULT_RE = re.compile(r"決算|説明会|四半期|中間|earnings|results|financial", re.I)
KST = timezone(timedelta(hours=9))


def _get(path, params, key):
    return json.loads(common.http_get(API + path, params={**params, "key": key}, timeout=30).decode("utf-8"))


def uploads_id(ch, key, cache):
    """채널 → 업로드 재생목록 id. handle(@...) 또는 channel_id 또는 query(검색, 100단위 — 처음 한 번)"""
    k = ch.get("channel_id") or ch.get("handle") or ch.get("query")
    if k in cache:
        return cache[k]
    if ch.get("channel_id"):
        r = _get("channels", {"part": "contentDetails", "id": ch["channel_id"]}, key)
    elif ch.get("handle"):
        r = _get("channels", {"part": "contentDetails", "forHandle": ch["handle"]}, key)
    else:
        s = _get("search", {"part": "snippet", "type": "channel", "q": ch["query"], "maxResults": 1}, key)
        cid = ((s.get("items") or [{}])[0].get("id") or {}).get("channelId")
        r = _get("channels", {"part": "contentDetails", "id": cid}, key) if cid else {}
    items = r.get("items") or []
    cache[k] = items[0]["contentDetails"]["relatedPlaylists"]["uploads"] if items else None
    return cache[k]


def poll(env=None, now=None):
    env = env or common.load_env()
    key = env.get("YOUTUBE_API_KEY")
    chans = (common.load_yaml("config/yt_ir_channels.yaml") or {}).get("channels") or []
    if not key:
        print("YouTube IR: 키 대기(YOUTUBE_API_KEY) — docs/TODO_MASTER.md 21-40")
        return []
    st = common.load_state("yt_ir", {"uploads": {}, "seen": {}})
    items, errors = [], []
    for ch in chans:
        try:
            pl = uploads_id(ch, key, st["uploads"])
            if not pl:
                errors.append(f"{ch['id']}: 채널 없음")
                continue
            r = _get("playlistItems", {"part": "snippet", "playlistId": pl, "maxResults": 10}, key)
            prev = st["seen"].get(ch["id"])
            ids = []
            for it in r.get("items") or []:
                sn = it.get("snippet") or {}
                vid = (sn.get("resourceId") or {}).get("videoId")
                ids.append(vid)
                if prev is None or vid in prev or not RESULT_RE.search(sn.get("title", "")):
                    continue
                t = datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00")).astimezone(KST)
                items.append(common.make_item(SRC, vid, f"https://www.youtube.com/watch?v={vid}", f"{ch['label']}（{ch.get('code', '')}） {sn.get('title', '')[:90]}",
                                              common.iso(t), "IR 자료", "ja",
                                              "공식 IR 채널 결산 영상 게시 — YouTube라 자체 전사 불가(약관·robots). 내용은 TradingView 전사·회사 Q&A 요지·PT로",
                                              extra={"entities_matched": [ch["id"]], "source_class": "IR 자료", "kind": "video", "platform": "youtube"}))
            st["seen"][ch["id"]] = sorted(set(prev or []) | {i for i in ids if i})[-200:]
        except Exception as exc:
            errors.append(f"{ch['id']}: {type(exc).__name__}")
    common.save_state("yt_ir", st)
    if errors and len(errors) == len(chans):
        raise RuntimeError("YouTube IR 전부 실패: " + ", ".join(errors[:5]))
    if errors:
        print("YouTube IR 일부 건너뜀:", ", ".join(errors))
    return items


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"{len(poll())}건")
