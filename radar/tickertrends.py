"""TickerTrends 대체 데이터 신호 — 소비·검색·소셜 관심의 가속 (마스터 지시 2026-11-12 "TickerTrends로 데이터 파이프라인을 만들어").

결정론 수집만(모델 없음), run_hourly 하루 1회. 설정 config/tickertrends.yaml(대상·신호 종류·알림 문턱).
  ① 대상마다 /signals 호출 → knowledge/models/tickertrends/latest.json(git 제외 아님 — 수치는 내부용, 아래 경계)
  ② 90일 가속·지속 점수가 둘 다 문턱을 넘고, 직전 회차엔 안 넘었던 대상만 inbox src-tickertrends → Pulse '관심도 가속'
경계: 약관이 내부 업무용 한정·제3자 공유 금지 — 항목에 internal_only를 달고, 기사·리포트·노션·공개 산출물에 수치를 옮기지 않는다.
      수치 저장 파일도 git에 올리지 않는다(knowledge/models/tickertrends/는 .gitignore).
키: TICKERTRENDS_API_KEY(유료 API, docs/TODO_MASTER.md) — 없으면 '키 대기'로 건너뛴다. 키는 헤더로만 보내고 출력·오류 메시지에 쓰지 않는다.
사용: py radar/tickertrends.py [--show]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

API = "https://api.tickertrends.io/signals"
OUT = common.ROOT / "knowledge" / "models" / "tickertrends"


def config():
    return common.load_yaml("config/tickertrends.yaml") or {}


def targets(cfg):
    out = list(cfg.get("entities") or [])
    if cfg.get("from_portfolio"):
        pf = common.load_yaml("config/portfolio.yaml") or {}
        out += [h["ticker"] for h in pf.get("holdings") or [] if h.get("ticker") and h.get("status") in ("보유", "관심")]
    return list(dict.fromkeys(out))[: int(cfg.get("max_calls", 40))]


def fetch(entity, sig, k):
    try:
        raw = common.http_get(API, {"entity": entity, "signal_type": sig}, headers={"Authorization": f"Bearer {k}"}, timeout=30)
    except Exception as exc:   # 키는 헤더에만 있지만 메시지는 종류만 남긴다
        raise RuntimeError(f"TickerTrends 호출 실패({type(exc).__name__})") from None
    d = json.loads(raw)
    if d.get("status") != "success":
        raise RuntimeError(f"TickerTrends 응답 {str(d.get('status'))[:40]}")
    return d.get("signal") or {}


def hot(s, a):
    try:
        return float(s.get("acceleration_90d")) >= a["acceleration_90d"] and float(s.get("persistence_score")) >= a["persistence_score"]
    except (TypeError, ValueError):
        return False


def run():
    k = common.load_env().get("TICKERTRENDS_API_KEY")
    if not k:
        common.record_health("tickertrends", True, "키 대기(TICKERTRENDS_API_KEY)")
        return "키 대기(TICKERTRENDS_API_KEY) — docs/TODO_MASTER.md"
    cfg, now = config(), common.now_kst()
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / "latest.json"
    old = json.loads(f.read_text(encoding="utf-8")).get("signals", {}) if f.exists() else {}
    new, errs, items = {}, [], []
    for e in targets(cfg):
        for sig in cfg.get("signal_types") or ["consumer_demand"]:
            key = f"{e}|{sig}"
            try:
                s = fetch(e, sig, k)
            except Exception as exc:
                errs.append(f"{e} {exc}")
                if key in old:
                    new[key] = old[key]
                continue
            new[key] = s
            if hot(s, cfg["alert"]) and not hot(old.get(key) or {}, cfg["alert"]) and old:
                items.append(common.make_item("src-tickertrends", f"{key}:{now.date()}", "https://tickertrends.io/",
                                              f"[관심도 가속] {e} {sig} — 90일 가속 {float(s['acceleration_90d']):+.0%}, 지속 {s['persistence_score']}",
                                              common.iso(now), "대체 데이터", "ko", f"KPI 연결: {', '.join(s.get('kpi_readthrough') or []) or '미확인'}",
                                              extra={"internal_only": True, "source_class": "대체 데이터(유료·내부용) — 관심은 실적이 아니다"}))
    f.write_text(json.dumps({"as_of": common.iso(now), "signals": new}, ensure_ascii=False, indent=1), encoding="utf-8")
    saved = common.save_new_items(items)
    common.record_health("tickertrends", not (errs and not new), f"신호 {len(new)} · 알림 {len(saved)}" + (f" · 실패 {len(errs)}" if errs else ""))
    return f"TickerTrends 신호 {len(new)} · 알림 {len(saved)}" + (f" · 실패 {len(errs)}" if errs else "")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--show" in sys.argv:
        p = OUT / "latest.json"
        print(p.read_text(encoding="utf-8") if p.exists() else "저장 없음")
    else:
        print(run())
