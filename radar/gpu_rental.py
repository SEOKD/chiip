"""GPU 렌털료 추적 — 제공사 공개 가격표 + Silicon Data 공개 지수 + TrendForce 보도자료 (마스터 지시 2026-11-10 "네비우스 GPU 렌탈료 파이프라인 …
GPU 제품별 렌털료를 추적해줘. 실리콘 데이터, 트렌드포스 데이터도 연결하는 파이프라인을 구축해").

원천(모두 robots.txt 허용 확인 2026-11-10, 공개 페이지만, 로그인·유료 데이터 없음):
  · Nebius  nebius.com/prices — GPU별 온디맨드·선점형(preemptible, 'from') 시간당 GPU 가격
  · CoreWeave coreweave.com/pricing — 노드(인스턴스) 시간당 가격 → GPU 수로 나눠 GPU당 환산(노드 가격도 함께 저장)
  · Lambda  lambda.com/pricing — 인스턴스(8x·4x·2x·1x) GPU당 가격, 1-Click Clusters 약정(2주~1년, GPU 수 구간) GPU당 가격
  · Silicon Data 공개 지수 카드(silicondata.com/products/silicon-index/*) — 헤드라인 값만 '인용'(일 1회). 데이터셋·API는 유료 계약 대상이라 쓰지 않는다
  · TrendForce 프레스센터 RSS(feed/Semiconductors.html) — GPU·HBM·DRAM·서버 가격 문구가 든 무료 보도자료 제목·요약만(유료 리포트 본문 수집 안 함)
단위: 모두 '달러/GPU·시간'으로 맞춘다. 맞출 수 없으면(NVL72 랙 '문의', 노드 단위만 있고 GPU 수 불명) 가격을 비우고 note에 '비교 불가'.
저장: knowledge/models/gpu_rental.csv(누적 스냅숏) · knowledge/models/gpu_rental_latest.json · outputs/gpu_rental/<날짜>.md(제품별 비교표)
알림: 같은 (제공사·GPU·구성·조건) 가격이 바뀌면 inbox src-gpu-rental, TrendForce 새 가격 보도자료는 src-trendforce-pr → Pulse '보도자료'.
사용: py radar/gpu_rental.py          # 수집·저장·변화 알림(run_hourly 360분)
      py radar/gpu_rental.py --table  # 최신 비교표 출력
"""
import csv
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

CSV = common.ROOT / "knowledge" / "models" / "gpu_rental.csv"
LATEST = common.ROOT / "knowledge" / "models" / "gpu_rental_latest.json"
OUTD = common.ROOT / "outputs" / "gpu_rental"
FIELDS = ["date", "provider", "gpu", "config", "term", "usd_per_gpu_hr", "node_usd_hr", "gpus_per_node", "note", "source_url", "retrieved_at"]
GPU_ORDER = ["GB300", "B300", "GB200", "B200", "H200", "GH200", "H100", "MI300X", "A100", "L40S", "RTX PRO 6000"]
SD_PAGES = ["https://www.silicondata.com/products/silicon-index/h100", "https://www.silicondata.com/products/silicon-index/b200"]
TF_RSS = "https://www.trendforce.com/feed/Semiconductors.html"
TF_RE = re.compile(r"\bGPU|rental|HBM|DRAM|NAND|server|AI chip|contract price|ASP|wafer", re.I)
PRICE_RE = re.compile(r"price|ASP|cost|rental|rise|increase|decline|QoQ|YoY", re.I)


def norm(name):
    s = name.upper()
    for g in ["GB300", "GB200", "GH200", "B300", "B200", "H200", "H100", "MI300X", "A100", "L40S", "RTX PRO 6000", "A6000", "A10", "V100"]:
        if re.search(r"(?<![A-Z0-9])" + re.escape(g) + r"(?![0-9])", s):
            return g
    return name.strip()


def _get(url):
    return common.http_get(url, timeout=40).decode("utf-8", "ignore")


def _money(s):
    m = re.search(r"\$\s?([0-9][0-9,]*\.?[0-9]*)", s or "")
    return float(m.group(1).replace(",", "")) if m else None


def nebius():
    url = "https://nebius.com/prices"
    t = _get(url).replace('\\"', '"')
    rows = []
    for tb in re.finditer(r'"content":\[(\["Item".*?\])\]', t):
        try:
            tab = json.loads("[" + tb.group(1) + "]")
        except ValueError:
            continue
        head = [h.lower() for h in tab[0]]
        if not any("gpu-hour" in h for h in head):
            continue
        for r in tab[1:]:
            if not r or "NVIDIA" not in r[0] and "AMD" not in r[0]:
                continue
            for j, h in enumerate(head):
                if "gpu-hour" not in h or j >= len(r):
                    continue
                term = "선점형(from, 최저 시작가)" if "preemptible" in h else ("온디맨드" if "on-demand" in h else h)
                p = _money(r[j])
                rows.append({"provider": "Nebius", "gpu": norm(r[0]), "config": r[0], "term": term, "usd_per_gpu_hr": p,
                             "note": "" if p is not None else "비교 불가(문의)", "source_url": url})
    return rows


def coreweave():
    url = "https://www.coreweave.com/pricing"
    s = html.unescape(re.sub(r"<script.*?</script>|<style.*?</style>", " ", _get(url), flags=re.S))
    s = re.sub(r"(\s*\|\s*)+", " | ", re.sub(r"<[^>]+>", " | ", s))
    rows, seen = [], set()
    for m in re.finditer(r"\| ((?:NVIDIA|AMD) [^|]{2,40}) \| On-Demand Price: \| (\$[0-9.,]+ \| )?/ Hour \| Spot Price: \| (\$[0-9.,]+|N/A) \|.{0,200}?\| (\d+)(?:\^\d+)? \| GPU Count", s):   # NVL72는 '4^1'(인스턴스당 GPU 4개)
        name, od, spot, n = m.group(1).strip(), _money(m.group(2) or ""), _money(m.group(3)), int(m.group(4))
        if name in seen:
            continue
        seen.add(name)
        rack = "NVL72" in name
        for term, p in (("온디맨드", od), ("스팟", spot)):
            if p is None and term == "스팟":
                continue
            rows.append({"provider": "CoreWeave", "gpu": norm(name), "config": name, "term": term,
                         "usd_per_gpu_hr": round(p / n, 2) if p is not None and n else None, "node_usd_hr": p, "gpus_per_node": n,
                         "note": ("인스턴스 가격÷GPU 수" + ("(NVL72 랙의 인스턴스 단위)" if rack else "")) if p is not None else "비교 불가(문의)",
                         "source_url": url})
    return rows


def lambda_():
    url = "https://lambda.com/pricing"
    t = _get(url)
    eff = re.search(r"These prices take effect ([A-Z][a-z]+ \d{1,2}, \d{4})", t)
    rows, inst = [], 0
    for tb in re.findall(r"<table.*?</table>", t, re.S):
        head = [re.sub(r"<[^>]+>", "", x).strip() for x in re.findall(r"<thead.*?</thead>", tb, re.S)[0:1] for x in re.findall(r"<th[^>]*>(.*?)</th>", x, re.S)] if "<thead" in tb else []
        body = re.findall(r"<tr[^>]*>(.*?)</tr>", tb, re.S)
        cluster = "DURATION" in [h.upper() for h in head]
        size = "" if cluster else (["8x", "4x", "2x", "1x"][inst] if inst < 4 else "")   # 인스턴스 표 순서 = 페이지의 8x·4x·2x·1x 탭
        inst += 0 if cluster else 1
        for r in body:
            th = re.findall(r"<th[^>]*>(.*?)</th>", r, re.S)
            cells = {a.upper(): html.unescape(re.sub(r"<[^>]+>", "", b)).strip() for a, b in re.findall(r'<td[^>]*data-label="([^"]+)"[^>]*>(.*?)</td>', r, re.S)}
            if not cells:
                continue
            p = _money(cells.get("PRICE/GPU/HR*", ""))
            name = html.unescape(re.sub(r"<[^>]+>", "", th[0])).strip() if th else ""
            if cluster:
                term = f"약정 {cells.get('DURATION', '')} · {cells.get('GPU COUNT', '')} GPU"
                cfg = name or "1-Click Cluster"
            else:
                term = "온디맨드" + (f"(시행 {eff.group(1)})" if eff else "")
                cfg = f"{name} {size} {cells.get('VRAM/GPU', '')}".strip()   # 같은 크기에 VRAM 다른 변형(A100 40·80GB)이 있다
            if not cfg:
                continue
            rows.append({"provider": "Lambda", "gpu": norm(cfg), "config": cfg, "term": term, "usd_per_gpu_hr": p,
                         "note": "" if p is not None else "비교 불가(문의)", "source_url": url})
    return rows


def silicon_data():
    rows, seen = [], set()
    for url in SD_PAGES:
        t = _get(url)
        for m in re.finditer(r"text-\[30px\][^>]*>\$([0-9.]+)<", t):
            pre = t[m.start() - 900:m.start()]
            ctx = re.sub(r"(\s*\|\s*)+", " | ", html.unescape(re.sub(r"<[^>]+>", " | ", pre[:pre.rfind("<")])))
            lab = re.search(r"\| ([A-Za-z0-9 ]{2,30}) \| Bloomberg ticker: \| ([A-Z0-9-]+) \| View \|\s*$", ctx)
            if not lab or lab.group(1) in seen:
                continue
            seen.add(lab.group(1))
            if "Token" in lab.group(1):
                continue
            rows.append({"provider": "Silicon Data 지수", "gpu": norm(lab.group(1)), "config": f"{lab.group(1)} 지수" + (f" {lab.group(2)}" if lab.group(2) != "--" else ""),
                         "term": "시장 지수(인용)", "usd_per_gpu_hr": float(m.group(1)), "note": "공개 페이지 헤드라인 값 인용 — 데이터셋·API는 유료", "source_url": url})
    return rows


def trendforce(st):
    x = _get(TF_RSS)
    seen = set(st.get("tf_seen") or [])
    items = []
    for it in re.findall(r"<item>(.*?)</item>", x, re.S):
        title = html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", (re.search(r"<title>(.*?)</title>", it, re.S) or [None, ""])[1])).strip()
        link = (re.search(r"<link>(.*?)</link>", it, re.S) or [None, ""])[1].strip()
        desc = html.unescape(re.sub(r"<!\[CDATA\[|\]\]>|<[^>]+>", "", (re.search(r"<description>(.*?)</description>", it, re.S) or [None, ""])[1])).strip()
        if not link or link in seen or not (TF_RE.search(title + " " + desc) and PRICE_RE.search(title + " " + desc)):
            continue
        seen.add(link)
        if st.get("tf_seen") is not None:   # 첫 실행은 기준선
            items.append(common.make_item("src-trendforce-pr", link.rsplit("/", 1)[-1], link, f"[TrendForce] {title}", common.iso(common.now_kst()), "보도자료", "en",
                                          desc[:400], extra={"source_class": "보도자료", "publisher": "TrendForce"}))
    st["tf_seen"] = sorted(seen)[-400:]
    return items


def key(r):
    return (r["provider"], r["config"], r["term"])


def table(rows):
    """제품별 비교표 — 달러/GPU·시간, 조건을 함께 적는다"""
    L = ["| GPU | 제공사 | 구성 | 조건 | $/GPU·시 | 비고 |", "|---|---|---|---|---|---|"]
    order = {g: i for i, g in enumerate(GPU_ORDER)}
    for r in sorted(rows, key=lambda r: (order.get(r["gpu"], 99), r["gpu"], r["provider"], r["term"])):
        if r["gpu"] not in order:
            continue
        p = "-" if r.get("usd_per_gpu_hr") in (None, "") else f"${float(r['usd_per_gpu_hr']):.2f}"
        L.append(f"| {r['gpu']} | {r['provider']} | {r['config']} | {r['term']} | {p} | {r.get('note') or ''} |")
    return "\n".join(L)


def run():
    st = common.load_state("gpu_rental", {})
    now = common.iso(common.now_kst())
    today = now[:10]
    rows, errs = [], []
    for name, fn in (("Nebius", nebius), ("CoreWeave", coreweave), ("Lambda", lambda_), ("Silicon Data", silicon_data)):
        try:
            got = fn()
            rows += got
            if not got:
                errs.append(f"{name} 0행(페이지 구조 변경?)")
        except Exception as exc:
            errs.append(f"{name} {type(exc).__name__}")
    for r in rows:
        r.update({"date": today, "retrieved_at": now})
    prev = {tuple(k.split("||")): v for k, v in (st.get("last") or {}).items()}
    alerts = []
    for r in rows:
        k, p = key(r), r.get("usd_per_gpu_hr")
        old = prev.get(k)
        if prev and old is not None and p is not None and abs(p - old) >= 0.005:
            ch = (p / old - 1) * 100 if old else 0
            alerts.append(common.make_item("src-gpu-rental", f"{'-'.join(k)}-{today}-{p}", r["source_url"],
                                           f"[GPU 렌털료] {r['provider']} {r['config']} {r['term']} ${old:.2f} → ${p:.2f}/GPU·시({ch:+.1f}%)",
                                           now, "보도자료", "ko", f"{r['gpu']} · {r.get('note') or ''}", extra={"source_class": "보도자료", "gpu": r["gpu"]}))
    try:
        alerts += trendforce(st)
    except Exception as exc:
        errs.append(f"TrendForce {type(exc).__name__}")
    if rows:
        new = not CSV.exists()
        with CSV.open("a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
            if new:
                w.writeheader()
            w.writerows(rows)
        LATEST.write_text(json.dumps({"as_of": now, "rows": rows, "errors": errs}, ensure_ascii=False, indent=1), encoding="utf-8")
        OUTD.mkdir(parents=True, exist_ok=True)
        (OUTD / f"{today.replace('-', '')}.md").write_text(f"# GPU 렌털료 비교 {today}\n\n단위 달러/GPU·시간. 공개 가격표 기준(세금 별도). Silicon Data는 시장 지수 인용.\n\n" + table(rows) + "\n", encoding="utf-8")
        st["last"] = {"||".join(key(r)): r.get("usd_per_gpu_hr") for r in rows if r.get("usd_per_gpu_hr") is not None}
    common.save_state("gpu_rental", st)
    saved = common.save_new_items(alerts) if alerts else []
    return f"GPU 렌털료 {len(rows)}행 · 변화·보도 알림 {len(saved)}" + (f" · 문제 {', '.join(errs)}" if errs else "")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--table" in sys.argv:
        d = json.loads(LATEST.read_text(encoding="utf-8")) if LATEST.exists() else {"rows": []}
        print(table(d["rows"]))
    else:
        print(run())
