"""Analysis 종목별 원천 수집·관문 (마스터 지시 2026-11-08 — 점검에서 지시문의 종목별 원천 15종 중 대부분을 건너뛰고도 datapack_check가 10/10을 준 것이 드러남 → "고쳐라")

config/analysis_sources.yaml의 원천을 종목마다 한 번에 모으고, 무엇을 돌렸는지 장부에 남긴다. v2_to_report --merge가 장부를 보고 빠진 원천이 있으면 멈춘다.
  script  결정론 스크립트를 돌려 출력을 radar/state/gather/<id>/<원천>.txt에 둔다(git 제외 — Exclusive 단서가 섞일 수 있다)
  read    장부·수집함을 읽어 이 종목 항목만 뽑는다
  model   MCP 원천 — 모델이 부른 뒤 --mark로 적는다
상태: ok · '해당 없음(이유)' · '실패: …'. 실패는 다시 돌리거나 이유를 붙여 '해당 없음(…)'으로 고친다. 지어내지 않는다.
사용: py scripts/tenbagger/gather.py <회사 id>                         # script·read 원천을 모두 돌린다
      py scripts/tenbagger/gather.py <회사 id> --only tg_channels,lobby  # 일부만 다시
      py scripts/tenbagger/gather.py --mark <회사 id> <원천> ok|"해당 없음(이유)" ["메모"]
      py scripts/tenbagger/gather.py --check <회사 id>                 # 빠진 원천(종료 코드 1)
      py scripts/tenbagger/gather.py <회사 id> --reuse                 # 3일 안 장부가 있으면 다시 돌리지 않는다(Pulse·Portfolio 등 모든 기능, 2026-11-11)
      py scripts/tenbagger/gather.py --market [--reuse]               # 시장·산업 원천(config market:) → radar/state/gather/_market/
"""
import argparse
import csv
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "config" / "analysis_sources.yaml"
OUT = ROOT / "radar" / "state" / "gather"
KST = timezone(timedelta(hours=9))
REGION = {"NASDAQ": "us", "NYSE": "us", "AMEX": "us", "KRX": "kr", "TSE": "jp", "TWSE": "tw", "TPEX": "tw", "SSE": "cn", "SZSE": "cn", "HKEX": "hk"}   # 중국·홍콩(2026-11-09) — 지역 미확인이면 지역 전용 원천이 모두 빠졌다
OK = re.compile(r"^(ok|해당 없음\(.+\))$")


def config():
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def now():
    return datetime.now(KST)


def company(entity):
    """이름·티커·상장 지역. datapack이 먼저, 없으면 TradingView 대응표"""
    dp_p = ROOT / "knowledge" / "models" / "companies" / entity / "datapack.json"
    dp = json.loads(dp_p.read_text(encoding="utf-8")) if dp_p.exists() else {}
    row = {}
    with (ROOT / "config" / "tradingview_symbols.csv").open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["entity_id"] == entity:
                row = r
                break
    ticker = str(dp.get("ticker") or row.get("ticker") or "")
    region = REGION.get(row.get("exchange", ""))
    if not region:
        region = {"₩": "kr", "¥": "jp", "NT$": "tw", "HK$": "hk", "CN¥": "cn"}.get(dp.get("currency_symbol"), "us" if ticker.isalpha() else "")
    name = str(dp.get("name") or row.get("name") or entity)
    return {"id": entity, "ticker": ticker, "name": name, "legal": row.get("name") or name, "region": region,
            "names": [x for x in dict.fromkeys([name, row.get("name") or ""]) if x]}


def applies(src, co):
    return src.get("region", "all") in ("all", co["region"])


def ledger_path(entity):
    return OUT / entity / "ledger.json"


def load_ledger(entity):
    p = ledger_path(entity)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"entity": entity, "sources": {}}


def save_ledger(entity, led):
    p = ledger_path(entity)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(led, ensure_ascii=False, indent=1), encoding="utf-8")


def _hits(text, co):
    """제목·본문에 이 회사가 나오는가 — 짧은 티커(2자 이하)는 이름으로만 잡는다"""
    t = str(text)
    if any(n and n.lower() in t.lower() for n in co["names"]):
        return True
    return len(co["ticker"]) >= 3 and re.search(rf"(?<![A-Za-z0-9]){re.escape(co['ticker'])}(?![A-Za-z0-9])", t) is not None


def read_radar_items(co, days=21):
    rows, cut = [], (now() - timedelta(days=days)).strftime("%Y%m%d")
    inbox = ROOT / "radar" / "inbox"
    for d in sorted(p for p in inbox.iterdir() if p.is_dir() and p.name.isdigit() and p.name >= cut) if inbox.exists() else []:
        for f in d.glob("*.json"):
            try:
                it = json.loads(f.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            if co["id"] in (it.get("entities_matched") or []) or _hits(it.get("title"), co):
                rows.append(f"{(it.get('published_at') or it.get('detected_at') or '')[:10]} [{it.get('source_id')}] {it.get('title')} {it.get('url')}")
    cards = []
    for f in (ROOT / "radar" / "cards").rglob("*.yaml"):
        s = f.read_text(encoding="utf-8", errors="ignore")
        if co["id"] in s or _hits(s[:4000], co):
            cards.append(str(f.relative_to(ROOT)))
    out = [f"수집함 {len(rows)}건(최근 {days}일)"] + sorted(set(rows), reverse=True)[:80] + [f"영향 카드 {len(cards)}건"] + sorted(cards)[-30:]
    return out, bool(rows or cards)


def read_pairs(co):
    hits = [str(f.relative_to(ROOT)) for f in (ROOT / "knowledge" / "pairs").glob("*.md") if co["id"] in (s := f.read_text(encoding="utf-8")) or _hits(s, co)]
    return hits, bool(hits)


def read_overhang(co):
    p = ROOT / "knowledge" / "models" / "portfolio" / "overhang.csv"
    if not p.exists():
        return [], False
    with p.open(encoding="utf-8", newline="") as f:
        rows = [",".join(r.values()) for r in csv.DictReader(f) if r.get("ticker") == co["ticker"]]
    return rows, bool(rows)


def read_retail(co):
    p = ROOT / "knowledge" / "models" / "discovery" / "retail_latest.json"
    if not p.exists():
        return ["retail_latest.json 없음 — radar/attention.py가 아직 만들지 않았다"], False
    d = json.loads(p.read_text(encoding="utf-8"))
    hit = {k: v for k, v in (d.get("companies") or d).items() if isinstance(v, dict) and (k in (co["id"], co["ticker"]))}
    return [json.dumps(hit, ensure_ascii=False)], bool(hit)


def read_ape(co):
    sys.path.insert(0, str(ROOT / "radar"))
    import portfolio
    got = portfolio.fetch_ape({co["ticker"]})
    return [json.dumps(got, ensure_ascii=False)], bool(got)


def read_cited(co):
    p = ROOT / "knowledge" / "models" / "estimates" / "cited.csv"
    if not p.exists():
        return [], False
    with p.open(encoding="utf-8", newline="") as f:
        rows = [",".join(r.values()) for r in csv.DictReader(f) if r.get("ticker") == co["ticker"]]
    return rows, bool(rows)


def read_exclusive(co):
    p = ROOT / "knowledge" / "exclusive" / "leads.yaml"
    if not p.exists():
        return [], False
    return [], False   # 2026-11-11 마스터 지시 — 1급 기밀, 분석 글에 쓰지 않는다(docs/channels/notion.md '1급 기밀·해설 피드')
    leads = (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("leads") or []
    # insider_like는 invest·public 금지(CLAUDE.md) — Analysis에 넣지 않는다. 원문 인용·취재원 표현은 쓰지 않는다
    rows = [f"{x.get('id')} {x.get('dated')} {x.get('title')} · 확인할 것: {' / '.join(x.get('check') or [])}"
            for x in leads if co["id"] in (x.get("entities") or []) and not x.get("insider_like")]
    return rows, bool(rows)


def read_korea_watch(co):
    p = ROOT / "knowledge" / "models" / "korea_watch" / "latest.json"
    if not p.exists():
        return [], False
    rows = [json.dumps(r, ensure_ascii=False) for r in json.loads(p.read_text(encoding="utf-8")).get("rows") or [] if co["id"] in json.dumps(r, ensure_ascii=False) or _hits(json.dumps(r, ensure_ascii=False), co)]
    return rows, bool(rows)


def read_jp_ir_qa(co):
    p = ROOT / "radar" / "state" / "jp_ir_qa.json"
    if not p.exists():
        return [], False
    c = (json.loads(p.read_text(encoding="utf-8")).get("companies") or {}).get(co["id"]) or {}
    return [json.dumps(c, ensure_ascii=False)[:6000]], bool(c)


READERS = {"radar_items": read_radar_items, "pairs": read_pairs, "overhang": read_overhang, "retail": read_retail, "ape": read_ape,
           "cited": read_cited, "exclusive": read_exclusive, "korea_watch": read_korea_watch, "jp_ir_qa": read_jp_ir_qa}


def run_one(src, co, cfg):
    out_dir = OUT / co["id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = now().isoformat(timespec="seconds")
    try:
        if src["kind"] == "script":
            cmd =[sys.executable] + _whole(src["cmd"], co, out_dir)
            p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=cfg.get("timeout_s", 240),
                               env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
            text = (p.stdout or "") + (f"\n[stderr]\n{p.stderr}" if p.stderr.strip() else "")
            (out_dir / f"{src['id']}.txt").write_text(text, encoding="utf-8")
            if p.returncode != 0:
                last = (p.stderr.strip() or p.stdout.strip()).splitlines()[-1:] or ["종료 코드 " + str(p.returncode)]
                return {"status": f"실패: {last[0][:200]}", "at": stamp}
            if src.get("fail_if") and re.search(src["fail_if"], text):
                return {"status": f"실패: {src['fail_if']} — 재료를 연결하거나 이유를 붙여 --mark", "at": stamp}
            return {"status": "ok", "at": stamp, "lines": len(text.splitlines())}
        lines, found = READERS[src["id"]](co)
        (out_dir / f"{src['id']}.txt").write_text("\n".join(lines), encoding="utf-8")
        return {"status": "ok" if found else "해당 없음(이 종목 항목 없음)", "at": stamp, "lines": len(lines)}
    except subprocess.TimeoutExpired:
        return {"status": f"실패: {cfg.get('timeout_s', 240)}초 초과", "at": stamp}
    except Exception as e:  # noqa: BLE001 — 원천 하나가 깨져도 나머지는 모은다
        return {"status": f"실패: {type(e).__name__}: {str(e)[:160]}", "at": stamp}


def _whole(cmd, co, out_dir):
    """명령 틀을 인자로 — {name}·{legal}은 띄어쓰기가 있어도 한 인자"""
    vals = {"id": co["id"], "ticker": co["ticker"], "name": co["name"], "legal": co["legal"], "out": str(out_dir)}
    return [re.sub(r"\{(\w+)\}", lambda m: vals[m.group(1)], a) for a in cmd.split()]


def gather(entity, only=None, workers=6):
    cfg, co = config(), company(entity)
    led = load_ledger(entity)
    led.update({"entity": entity, "ticker": co["ticker"], "region": co["region"], "at": now().isoformat(timespec="seconds")})
    todo = [s for s in cfg["sources"] if s["kind"] in ("script", "read") and (not only or s["id"] in only)]
    for s in [s for s in todo if not applies(s, co)]:
        led["sources"][s["id"]] = {"status": f"해당 없음({co['region'] or '지역 미확인'} 상장 — {s['region']} 전용)", "at": led["at"]}
    run = [s for s in todo if applies(s, co)]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for s, res in zip(run, ex.map(lambda s: run_one(s, co, cfg), run)):
            led["sources"][s["id"]] = res
    save_ledger(entity, led)
    return led, co


def missing(entity, cfg=None, today=None):
    """merge를 막는 원천 — 해당 원천 중 ok·'해당 없음(이유)'가 아닌 것, 장부가 오래됐으면 전부"""
    cfg, led, co = cfg or config(), load_ledger(entity), company(entity)
    today = today or now()
    at = led.get("at")
    if not at or (today - datetime.fromisoformat(at)).days > cfg.get("max_age_days", 3):
        return [f"장부 없음·{cfg.get('max_age_days', 3)}일 초과 — py scripts/tenbagger/gather.py {entity}"]
    out = []
    for s in cfg["sources"]:
        st = (led["sources"].get(s["id"]) or {}).get("status", "")
        if s["kind"] == "model" or applies(s, co):
            if not OK.match(st):
                out.append(f"{s['id']}({st or '기록 없음'})")
    return out


def mark(entity, src, status, note=""):
    cfg = config()
    if src not in {s["id"] for s in cfg["sources"]}:
        raise SystemExit(f"모르는 원천: {src} — config/analysis_sources.yaml")
    if not OK.match(status):
        raise SystemExit("상태는 ok 또는 '해당 없음(이유)'")
    led = load_ledger(entity)
    led["sources"][src] = {"status": status, "at": now().isoformat(timespec="seconds"), "note": note}
    led.setdefault("at", led["sources"][src]["at"])
    save_ledger(entity, led)


def market(reuse=False):
    """시장·산업 원천(종목 무관) — 모든 기능이 쓴다(2026-11-11 마스터 지시)"""
    cfg, out_dir = config(), OUT / "_market"
    out_dir.mkdir(parents=True, exist_ok=True)
    led_p = out_dir / "_ledger.json"
    led = json.loads(led_p.read_text(encoding="utf-8")) if led_p.exists() else {"sources": {}}
    if reuse and led.get("at") and (now() - datetime.fromisoformat(led["at"])).total_seconds() < 6 * 3600:
        return led, True
    co = {"id": "_market", "ticker": "", "name": "", "legal": ""}
    srcs = [dict(s, kind="script") for s in cfg.get("market") or []]
    with ThreadPoolExecutor(max_workers=5) as ex:
        for s, res in zip(srcs, ex.map(lambda s: run_one(s, co, cfg), srcs)):
            led["sources"][s["id"]] = res
    led["at"] = now().isoformat(timespec="seconds")
    led_p.write_text(json.dumps(led, ensure_ascii=False, indent=1), encoding="utf-8")
    return led, False


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("entity", nargs="?")
    ap.add_argument("--only")
    ap.add_argument("--mark", nargs="+", metavar="ARG")
    ap.add_argument("--check")
    ap.add_argument("--reuse", action="store_true")
    ap.add_argument("--market", action="store_true")
    a = ap.parse_args(argv)
    if a.mark:
        if len(a.mark) < 3:
            raise SystemExit("--mark <회사 id> <원천> <상태> [메모]")
        mark(a.mark[0], a.mark[1], a.mark[2], " ".join(a.mark[3:]))
        print(f"[원천] {a.mark[0]} {a.mark[1]} = {a.mark[2]}")
        return 0
    if a.check:
        m = missing(a.check)
        print("[원천 관문] " + ("통과" if not m else "빠짐: " + " · ".join(m)))
        return 1 if m else 0
    if a.market:
        led, cached = market(a.reuse)
        print(f"[시장 원천] {'6시간 안 장부 재사용' if cached else '수집'} → {OUT / '_market'}")
        for k, v in led["sources"].items():
            print(f"  {k}: {v['status']}")
        return 0
    if not a.entity:
        ap.error("회사 id")
    if a.reuse and not a.only and not missing(a.entity):
        print(f"[원천 수집] {a.entity} 3일 안 장부 재사용 → {OUT / a.entity}")
        return 0
    led, co = gather(a.entity, set(a.only.split(",")) if a.only else None)
    print(f"[원천 수집] {a.entity} {co['ticker']} ({co['region'] or '지역 미확인'}) → {OUT / a.entity}")
    for k, v in led["sources"].items():
        print(f"  {k}: {v['status']}" + (f" · {v.get('lines')}줄" if v.get("lines") else ""))
    m = missing(a.entity)
    print("[원천 관문] " + ("통과" if not m else "남음: " + " · ".join(m)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
