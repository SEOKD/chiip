"""대만 원문 공시(重大訊息) — Chiip Ten-bagger 발굴·커버리지 대만 종목 (마스터 지시 2026-10-29 "발굴하고 관련 보도(반드시 원문)를 팔로업하라").

TWSE OpenAPI 上市公司每日重大訊息(t187ap04_L, 공식 공개 API)에서 config/discovery.yaml·config/coverage.yaml의 대만 종목만 거른다.
회사가 직접 낸 공시라 '원문'이다(event_gate의 1차 자료). 월매출은 src-twse-monthly가 따로 받는다. TPEx(상장 장외) 종목은 다음 단계.

법설회(法人說明會) 확보 절차(마스터 지시 2026-10-30, knowledge/methods/tw_hk_ir_qa_procedure.md): '召開法人說明會' 공시를 따로 표시하고
개최일·自辦/受邀·주최 증권사·影音 예정을 뽑아 radar/state/tw_ir_profile.json에 쌓는다(MOPS 法人說明會一覽表는 자동 수집하지 않는다 — 구 사이트 robots 전면 금지).
"""
import hashlib
import re
from datetime import datetime

from pollers import common

SRC = "src-tw-disclosure"
API = "https://openapi.twse.com.tw/v1/opendata/t187ap04_L"


def tw_codes():
    out = {}
    for t in (common.load_yaml("config/discovery.yaml") or {}).get("themes") or []:
        for c in t.get("candidates") or []:
            if c.get("market") == "tw":
                out[str(c["code"])] = c
    for c in (common.load_yaml("config/coverage.yaml") or {}).get("companies") or []:
        if c.get("market") == "tw":
            out[str(c["code"])] = c
    return out


def roc_to_iso(d, t="0"):
    """민국 날짜 1151028 + 시각 70003 → 2026-10-28T07:00:03+08:00"""
    d, t = str(d).strip(), str(t).strip().zfill(6)
    y, m, dd = int(d[:-4]) + 1911, int(d[-4:-2]), int(d[-2:])
    return datetime(y, m, dd, int(t[:2]), int(t[2:4]), int(t[4:6])).isoformat() + "+08:00"


CONF_RE = re.compile(r"法人說明會|法說會|業績說明會|investor conference", re.I)
INVITED_RE = re.compile(r"受邀|應邀|邀請")
BROKER_RE = re.compile(r"([一-鿿A-Za-z&．.]{2,16}?(?:證券|投顧|銀行|Securities|Capital))")
DATE_RE = re.compile(r"(\d{2,4})\s*[年/.-]\s*(\d{1,2})\s*[月/.-]\s*(\d{1,2})")
VIDEO_RE = re.compile(r"影音|錄影|直播|webcast|視訊", re.I)
EN_RE = re.compile(r"英文|English", re.I)


def parse_conference(text):
    """重大訊息 說明에서 법설회 사실만 뽑는다 — 개최일(西元)·自辦/受邀·주최 증권사·影音 언급·영문 진행 언급. 없는 건 None(추측 금지)"""
    s = " ".join(str(text or "").split())
    m = DATE_RE.search(s)
    day = None
    if m:
        y = int(m.group(1))
        y = y + 1911 if y < 1911 else y
        try:
            day = datetime(y, int(m.group(2)), int(m.group(3))).date().isoformat()
        except ValueError:
            day = None
    invited = bool(INVITED_RE.search(s))
    b = BROKER_RE.search(s) if invited else None
    broker = re.split(r"參加|出席|邀請|受邀|應邀|之|由|於", b.group(1))[-1] if b else None   # '本公司受邀參加凱基證券' → '凱基證券'
    return {"date": day, "host": "受邀" if invited else "自辦", "broker": broker if broker and len(broker) > 2 else None,
            "video": bool(VIDEO_RE.search(s)), "english": bool(EN_RE.search(s))}


def update_profile(code, name, conf, announced):
    """법설회 IR 프로필(radar/state/tw_ir_profile.json): 최근 공고·연간 횟수(빈도)·自辦/受邀·影音 언급"""
    st = common.load_state("tw_ir_profile", {})
    p = st.setdefault(code, {"name": name, "events": []})
    key = (conf.get("date") or announced[:10])
    if key not in [e.get("date") for e in p["events"]]:
        p["events"] = (p["events"] + [dict(conf, date=key, announced=announced)])[-12:]
    yr = sorted({e["date"][:4] for e in p["events"] if e.get("date")})
    last_year = [e for e in p["events"] if e.get("date", "")[:4] == (yr[-1] if yr else "")]
    p["freq_per_year"] = len(last_year)
    p["freq"] = "분기" if len(last_year) >= 4 else ("반기" if len(last_year) >= 2 else "연")   # 한 해 안에서 센 값 — 첫해는 과소
    p["host_mix"] = sorted({e["host"] for e in p["events"]})
    p["video_seen"] = any(e.get("video") for e in p["events"])
    common.save_state("tw_ir_profile", st)
    return p


def poll(env=None):
    import json
    codes = tw_codes()
    rows = json.loads(common.http_get(API, timeout=30))
    items = []
    for r in rows:
        code = str(r.get("公司代號", "")).strip()
        if code not in codes:
            continue
        c = codes[code]
        subj = " ".join(str(r.get("主旨 ") or r.get("主旨") or "").split())
        title = f"{r.get('公司名稱', c.get('name'))}({code}) 重大訊息: {subj}"
        uid = hashlib.sha1(f"{code}|{r.get('發言日期')}|{r.get('發言時間')}|{subj}".encode()).hexdigest()[:16]
        when = roc_to_iso(r.get("發言日期"), r.get("發言時間"))
        extra = {"entities_matched": [c["id"]], "publisher": "TWSE 重大訊息"}
        if CONF_RE.search(subj):   # 召開法人說明會 — 법설회 확보 절차 시작점(펄스 ⑥, 등급은 모델이 확보 후 부여)
            conf = parse_conference(f"{subj} {r.get('說明', '')}")
            update_profile(code, c.get("name"), conf, when)
            extra.update({"ir_event": "法說會", "conference": conf, "source_class": "IR 질의응답"})
            title = f"🎙 {r.get('公司名稱', c.get('name'))}({code}) 法說會 공고 — {conf['date'] or '일자 미확인'} {conf['host']}" + (f"·{conf['broker']}" if conf["broker"] else "")
        items.append(common.make_item(SRC, uid, f"{API}#{code}-{r.get('發言日期')}-{r.get('發言時間')}", title,
                                      when, "공시", "zh", " ".join(str(r.get("說明", "")).split())[:200], extra=extra))
    return items
