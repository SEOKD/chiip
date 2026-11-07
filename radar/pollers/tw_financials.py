"""대만 공시 재무 — 분기 손익·재무상태 (마스터 지시 2026-11-07 "한국 DART와 같은 대만 전자공시시스템에도 연결해 대만 AI 밸류체인 기업들의 어닝 및 재무 데이터를 가져올 수 있는 파이프라인을 구축해라")

TWSE·TPEx OpenAPI(정부 데이터 개방 경로, 키 불필요)의 綜合損益表·資產負債表(一般業)에서 감시 목록 대만 종목만 거른다.
두 표는 '가장 최근 분기' 한 장만 준다. 손익은 1월부터 누계(YTD)라 분기 값은 같은 해 직전 누계와의 차이로 만든다 — 직전 누계가 없으면 그 분기는 비운다(추측 금지).
그래서 이력은 회차마다 쌓인다. 과거 분기는 MOPS 약관상 자동으로 받지 않는다(config/tw_filings.yaml sources.mops). 현금흐름표는 공개 OpenAPI에 없다.
이사회 재무보고 승인 공고(重大訊息 第31款, tw_disclosure가 넘긴다)는 표보다 며칠 먼저 나와 누계 매출·이익·EPS·자산을 먼저 채우고, 표가 오면 표 값으로 바꾼다.
저장 knowledge/models/tw_filings/<코드>.json(천 대만달러 원값). quarters_hist 호환 출력은 원 단위(×1000).
사용: py radar/pollers/tw_financials.py --run · --status · --export <코드> <파일>  (그다음 py scripts/tenbagger/quarters.py --put <회사 id> <파일>)
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pollers import common  # noqa: E402

SRC = "src-tw-financials"
OUT = common.ROOT / "knowledge" / "models" / "tw_filings"
MONTHLY = common.ROOT / "knowledge" / "models" / "mirror_monthly.csv"
TWSE = "https://openapi.twse.com.tw/v1/opendata/"
TPEX = "https://www.tpex.org.tw/openapi/v1/"
TABLES = {"twse": {"is": TWSE + "t187ap06_L_ci", "bs": TWSE + "t187ap07_L_ci"},
          "tpex": {"is": TPEX + "mopsfin_t187ap06_O_ci", "bs": TPEX + "mopsfin_t187ap07_O_ci"}}
IS_FIELDS = {"rev": "營業收入", "cogs": "營業成本", "gp": "營業毛利（毛損）淨額", "opex": "營業費用", "other": "其他收益及費損淨額",
             "op": "營業利益（損失）", "nonop": "營業外收入及支出", "pretax": "稅前淨利（淨損）", "tax": "所得稅費用（利益）",
             "ni": "本期淨利（淨損）", "ni_parent": "淨利（淨損）歸屬於母公司業主", "eps": "基本每股盈餘（元）"}
BS_FIELDS = {"ca": "流動資產", "assets": "資產總計", "cl": "流動負債", "liab": "負債總計", "capital": "股本",
             "equity_parent": "歸屬於母公司業主之權益合計", "equity": "權益總計", "bvps": "每股參考淨值"}
NOTICE_FIELDS = {"rev": r"營業收入", "gp": r"營業毛利", "op": r"營業利益", "pretax": r"稅前淨利", "ni_parent": r"歸屬於母公司業主淨利",
                 "ni": r"本期止本期淨利", "eps": r"基本每股盈餘", "assets": r"期末總資產", "liab": r"期末總負債", "equity_parent": r"期末歸屬於母公司業主之權益"}
NOTICE_RE = re.compile(r"董事會.*(通過|決議).*(財務報告|財務報表|自結)|財務報告.*董事會")
QEND = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
PER_SHARE = ("eps", "bvps")


def _codes(rows, key="code"):
    return [str(r.get(key) or "").split(".")[0] for r in rows or []]


def universe():
    """감시 목록의 대만 종목 {코드: {id, name}} — IR 프로필·밸류·어닝·발굴·거울 매트릭스·추가 목록을 합친다"""
    out = {}
    add = lambda code, cid, name: out.setdefault(str(code), {"id": cid, "name": name}) if str(code).isdigit() else None
    for cid, c in ((common.load_yaml("config/tw_hk_ir.yaml") or {}).get("companies") or {}).items():
        if c.get("market") == "tw":
            add(c["code"], cid, c.get("name"))
    for f in ("config/valuation.yaml", "config/earnings_watch.yaml"):
        doc = common.load_yaml(f) or {}
        for r in (doc.get("universe") or []) + (doc.get("extra") or []):
            if isinstance(r, dict) and r.get("region") == "TW" and r.get("code"):
                add(str(r["code"]).split(".")[0], r.get("id"), r.get("name"))
    for t in (common.load_yaml("config/discovery.yaml") or {}).get("themes") or []:
        for c in t.get("candidates") or []:
            if c.get("market") == "tw":
                add(c["code"], c.get("id"), c.get("name"))
    for groups in ((common.load_yaml("config/mirror_matrix.yaml") or {}).get("mirrors") or {}).values():
        for g in groups:
            for code in g.get("tw_codes") or []:
                add(code, None, None)
    for c in (common.load_yaml("config/tw_filings.yaml") or {}).get("extra") or []:
        add(c["code"], c.get("id"), c.get("name"))
    local = {}
    if MONTHLY.exists():   # 거울 매트릭스에만 있는 종목은 월매출 표의 한자 이름으로 찾는다
        with MONTHLY.open(encoding="utf-8", newline="") as f:
            local = {r["tw_code"]: r["name"] for r in csv.DictReader(f)}
    for code, v in out.items():
        v["name"] = ko_name(local.get(code), v["name"])
    return out


def ko_name(local, fallback=None):
    """한자 회사명 → 한국어 표기(config/tw_hk_names.yaml), 영문 이름 → config/tw_filings.yaml ko_names. 둘 다 없으면 fallback"""
    names = (common.load_yaml("config/tw_hk_names.yaml") or {}).get("names") or {}
    en = (common.load_yaml("config/tw_filings.yaml") or {}).get("ko_names") or {}
    return names.get(str(local or "").rstrip("*")) or en.get(fallback) or fallback


def num(v):
    s = str(v if v is not None else "").replace(",", "").strip()
    try:
        return float(s) if s not in ("", "-", "--") else None
    except ValueError:
        return None


def quarter_key(year, season):
    """민국 115·3 → '2026Q3'"""
    return f"{int(year) + 1911}Q{int(season)}"


def row_code(r):
    return str(r.get("公司代號") or r.get("SecuritiesCompanyCode") or "").strip()


def row_quarter(r):
    return quarter_key(r.get("年度") or r.get("Year"), r.get("季別") or r.get("Season"))


def parse_rows(rows, fields, codes):
    """OpenAPI 표 → {코드: (분기, 회사명, {필드: 값})}"""
    out = {}
    for r in rows:
        code = row_code(r)
        if code in codes:
            out[code] = (row_quarter(r), r.get("公司名稱") or r.get("CompanyName"), {k: num(r.get(v)) for k, v in fields.items()})
    return out


def parse_notice(text):
    """이사회 재무보고 승인 공고 說明 → (분기, {필드: 값}). 기간이 1/1부터가 아니거나 못 읽으면 (None, {})"""
    s = str(text or "")
    m = re.search(r"(\d{2,3})/01/01\s*~\s*(\d{2,3})/(\d{2})/(\d{2})", s)
    if not m or m[1] != m[2] or f"{m[3]}-{m[4]}" not in QEND.values():
        return None, {}
    q = {v: k for k, v in QEND.items()}[f"{m[3]}-{m[4]}"]
    vals = {}
    for line in s.splitlines():
        if ":" not in line and "：" not in line:
            continue
        head, val = re.split(r"[:：]", line, maxsplit=1)
        for k, rx in NOTICE_FIELDS.items():
            if k not in vals and re.search(rx, head):
                vals[k] = num(val)
    return quarter_key(m[1], q), {k: v for k, v in vals.items() if v is not None}


def path_of(code):
    return OUT / f"{code}.json"


def load(code):
    f = path_of(code)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def save(doc):
    OUT.mkdir(parents=True, exist_ok=True)
    path_of(doc["code"]).write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


def merge(doc, quarter, part, vals, basis, source, when):
    """한 분기 누계에 값을 넣는다. 표(statement) 값은 공고(board_notice) 값을 덮고, 공고는 표를 덮지 않는다. 바뀌었으면 True"""
    e = doc["ytd"].setdefault(quarter, {"end": f"{quarter[:4]}-{QEND[int(quarter[-1])]}", "is": {}, "bs": {}, "basis": {}})
    if e["basis"].get(part) == "statement" and basis != "statement":
        return False
    if e[part] == vals and e["basis"].get(part) == basis:
        return False
    e[part], e["basis"][part] = vals, basis
    e.setdefault("sources", {})[part] = source
    e["retrieved"] = when
    return True


def new_doc(code, meta, local, market):
    return {"code": code, "id": meta.get("id"), "name": ko_name(local, meta.get("name")), "market": market,
            "unit": "NT$ thousand", "currency": "TWD", "ytd": {}}


def record_notice(code, local, text, url, when, market="twse"):
    """tw_disclosure가 부른다 — 第31款 재무보고 승인 공고의 누계 숫자를 저장. 저장했으면 분기 키"""
    meta = universe().get(code)
    quarter, vals = parse_notice(text)
    if not meta or not quarter or "rev" not in vals:
        return None
    doc = load(code) or new_doc(code, meta, local, market)
    bs = {k: vals.pop(k) for k in ("assets", "liab", "equity_parent") if k in vals}
    changed = merge(doc, quarter, "is", vals, "board_notice", url, when)
    if bs:
        changed = merge(doc, quarter, "bs", bs, "board_notice", url, when) or changed
    if changed:
        save(doc)
    return quarter


def quarters(doc):
    """누계 → 분기 값. 손익은 같은 해 직전 누계를 빼고(1분기는 그대로), 재무상태는 시점 값 그대로. 직전 누계가 없으면 손익 칸을 비운다"""
    ytd, out = doc.get("ytd") or {}, []
    for k in sorted(ytd):
        e, y, n = ytd[k], k[:4], int(k[-1])
        prev = ytd.get(f"{y}Q{n - 1}", {}).get("is") if n > 1 else {}
        flow = {}
        if prev is not None:
            for f, v in (e.get("is") or {}).items():
                p = prev.get(f) if n > 1 else 0.0
                flow[f] = None if v is None or p is None else round(v - p, 4 if f in PER_SHARE else 2)
        out.append({"quarter": k, "period": e["end"], **{f: flow.get(f) for f in IS_FIELDS}, **(e.get("bs") or {}),
                    "basis": e.get("basis"), "derived": n > 1})
    return out


def quarters_hist(doc):
    """datapack quarters_hist 모양(scripts/tenbagger/quarters.py --put 입력) — 원 단위, 매출 있는 분기만"""
    x = lambda v: None if v is None else v * 1000
    q = [{"period": r["period"], "rev": x(r["rev"]), "cogs": x(r["cogs"]), "gp": x(r["gp"]), "sga": None, "rd": None, "da": None,
          "other": x(r["other"]), "op": x(r["op"]), "opex": x(r["opex"])} for r in quarters(doc) if r.get("rev")]
    return {"source": f"{'TWSE' if doc['market'] == 'twse' else 'TPEx'} OpenAPI 누계 차분(radar/pollers/tw_financials.py)",
            "key": f"TW_{doc['code']}", "currency": "TWD", "q": q}


def monthly_ytd(code, period):
    """거울 매트릭스 월매출 표의 같은 달 누계(천 대만달러) — 분기 매출 대조용"""
    if not MONTHLY.exists():
        return None
    with MONTHLY.open(encoding="utf-8", newline="") as f:
        hit = [r for r in csv.DictReader(f) if r["tw_code"] == code and r["period"] == period]
    return num(hit[-1]["ytd_k_twd"]) if hit else None


def collect(codes, fetch=None):
    """두 시장의 손익·재무상태 표 → {코드: {'market', 'is': (분기, 이름, 값), 'bs': ...}}, 오류 목록"""
    fetch = fetch or (lambda u: json.loads(common.http_get(u, timeout=60)))
    got, errors = {}, []
    for market, urls in TABLES.items():
        for part, url in urls.items():
            try:
                rows = fetch(url)
            except Exception as e:
                errors.append(f"{market} {part}: {type(e).__name__}")
                continue
            for code, v in parse_rows(rows, IS_FIELDS if part == "is" else BS_FIELDS, codes).items():
                got.setdefault(code, {"market": market})[part] = v
    return got, errors


def run(fetch=None):
    codes = universe()
    got, errors = collect(codes, fetch)
    if errors and not got:
        common.record_health(SRC, False, "; ".join(errors))
        raise RuntimeError("대만 재무 표를 하나도 받지 못했다: " + "; ".join(errors))
    when, changed = common.iso(common.now_kst()), []
    for code, parts in got.items():
        local = next((v[1] for v in (parts.get("is"), parts.get("bs")) if v), None)
        doc = load(code) or new_doc(code, codes[code], local, parts["market"])
        name = ko_name(local, codes[code].get("name"))
        hit, doc["name"] = doc.get("name") != name, name
        for part in ("is", "bs"):
            if part in parts:
                q, _, vals = parts[part]
                hit = merge(doc, q, part, vals, "statement", TABLES[parts["market"]][part], when) or hit
        if hit:
            save(doc)
            changed.append(code)
    common.record_health(SRC, True, None)
    return len(changed), len(got), errors


def status():
    lines = []
    for code, meta in sorted(universe().items()):
        doc = load(code)
        if not doc:
            lines.append(f"{code} {meta.get('name') or ''} — 아직 공시 재무 없음")
            continue
        q = quarters(doc)[-1]
        e = doc["ytd"][q["quarter"]]
        mo = monthly_ytd(code, e["end"][:7])
        chk = "" if mo is None or not e["is"].get("rev") else f" · 월매출 누계 대조 {e['is']['rev'] / mo - 1:+.2%}"
        eok = lambda v: "미확인" if v is None else f"{v / 1e5:,.1f}억 대만달러"   # 천 대만달러 → 억 대만달러
        lines.append(f"{code} {doc['name']} {q['quarter']} 누계 매출 {eok(e['is'].get('rev'))} · 영업이익 {eok(e['is'].get('op'))}"
                     f" · 분기 값 {'있음' if q['rev'] is not None else '직전 누계 없어 비움'} · 근거 {e['basis'].get('is', '-')}{chk}")
    return lines


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--export", nargs=2, metavar=("CODE", "FILE"))
    a = ap.parse_args()
    if a.run:
        n, seen, errors = run()
        print(f"대만 공시 재무: 바뀐 종목 {n}, 표에 있던 종목 {seen}, 오류 {errors or '없음'}")
    if a.status:
        print("\n".join(status()))
    if a.export:
        doc = load(a.export[0]) or sys.exit(f"{a.export[0]} 저장분 없음")
        Path(a.export[1]).write_text(json.dumps(quarters_hist(doc), ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"분기 {len(quarters_hist(doc)['q'])}개 — quarters.py --put은 8개 이상일 때만 받는다")


if __name__ == "__main__":
    main()
