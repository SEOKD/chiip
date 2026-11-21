"""Chiip Pulse — GPU 렌털비 일일 추이 그래프 (마스터 지시 2026-11-19 "Pulse로 매일 GPU 렌탈비 추이도 보내줘. H100, H200, B200, B300
네 개 상품만 가져오고 Nebius, CoreWeave, AWS 세 개의 서비스에서 집계해줘")

원천(모두 공개 가격표, 로그인·유료 데이터 없음):
  · knowledge/models/gpu_rental.csv — radar/gpu_rental.py가 6시간마다 세 곳 가격표를 직접 수집(2026-11-10~)
  · knowledge/models/gpu_rental_wayback.csv — 인터넷 아카이브(web.archive.org, robots 허용)에 남은 같은 가격표 스냅숏을
    --backfill로 역수집해 그 이전 구간을 채운다. 스냅숏 주소를 행마다 남긴다. 아카이브에 AWS 가격 JSON은 2026-09부터라
    AWS는 공식 가격표 API(Price List, 공개·키 없음)의 월별 판으로 채운다(aws_pricelist, 관측일 = 판 게시일).
가격: 세 곳 모두 온디맨드 정가 $/GPU·시. CoreWeave·AWS는 8 GPU 노드(인스턴스) 가격 ÷ 8, AWS는 미국 동부·리눅스.
  선점형·스팟·약정가는 뺀다(2026-11-16 마스터 지시 "가격 종류를 하나로 통일"과 같은 원칙). '문의'는 값 없음.
정가는 계단식으로 바뀐다 — 관측일 사이는 직전 관측값을 잇고(계단선), 관측일에 점을 찍는다.
  바뀐 날짜는 '두 관측일 사이'로만 안다. 그 구간을 change 목록에 함께 적는다.
시장 지수(2026-11-21 마스터 지시 "GPU 임대료 집계가 잘 안 되는 것 같다. 추이가 제대로 안 나오기 때문이다. 이유를 점검하고 문제를 해결하라"):
  세 곳 정가는 몇 달에 한 번만 바뀐다(CoreWeave·AWS는 연중 그대로) — 정가만으로는 시장 임대료의 움직임이 보이지 않는다.
  그래서 각 칸에 Silicon Data 시장 지수(거래 가격 기반 $/GPU·시, 공개 페이지 헤드라인 인용 — 데이터셋·API는 유료라 쓰지 않는다)를
  회색 점선 '참고선'으로 함께 그린다. 지수 과거값은 같은 공개 페이지의 인터넷 아카이브 스냅숏(2026-07-28~)으로 채운다(--backfill-index).
  정가가 두 관측 사이에서 바뀌면 그 구간을 점선 사선으로 그린다(그 사이 어느 날 바뀜 — 바뀐 날을 지어내지 않는다).
결정론: 매일 10:00~11:00 KST 첫 Pulse 회차에 due(주말 포함). 그림은 START(2026-01-01)부터 오늘까지 — 해가 바뀌어도 리셋하지 않고 이어 그린다. 숫자·그림은 여기서, 풀이 2~4문장(read)만 모델 몫.
사용: py radar/gpu_daily.py --backfill [2026-01-01]   # 아카이브 역수집(요청 사이 6초, 이어받기 가능)
      py radar/gpu_daily.py --backfill-index [2026-01-01]   # Silicon Data 지수 아카이브 역수집
      py radar/gpu_daily.py --backfill-flopper   # Flopper 제공사 중앙값 30일치(페이지에 든 일별 값)
      py radar/gpu_daily.py --backfill-ornn      # Ornn 실거래 지수 공개 이력(3개월) — 내부용
      py radar/gpu_daily.py --chart [시작일]           # 그림만 그려 경로·요약 출력
      py radar/gpu_daily.py --status                  # Pulse 관문(JSON)
      py radar/gpu_daily.py --send <json>             # {"read": "..."} → 그림+설명 마스터 개인 봇
"""
import csv
import gzip
import html
import json
import math
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402
import gpu_rental  # noqa: E402

STATE = "gpu_daily"
GPUS = ["H100", "H200", "B200", "B300"]
PROVS = ["Nebius", "CoreWeave", "AWS"]
IDX = "Silicon Data 지수"   # 시장 지수 참고선(2026-11-21) — 제공사가 아니다
ORN = "Ornn 지수"   # 실거래 정산 일일 지수(radar/gpu_rental.ornn) — 내부용: 마스터 개인 봇 그림·캡션만(약관, 마스터 결정 2026-11-21 "붙여")
FLP = "Flopper 시장 중앙값"   # 제공사 30여 곳 온디맨드 최저가의 그날 중앙값(radar/gpu_rental.flopper, 2026-11-21 마스터 지시 "일일 데이터 변동이 있는 파이프라인을 찾고 …")
# 참고선(매일 움직이는 시장 값) — (이름, 수집 term 앞부분, 색, 점선, 끝 이름표 꼬리, 범례). 정가와 정의가 달라 직접 비교하지 않는다
REFS = [(IDX, "시장 지수", (0.42, 0.42, 0.40), "[3 2] 0", " 지수", "시장 지수(Silicon Data)"),
        (FLP, "시장 중앙값", (0.22, 0.22, 0.21), "[1 1.6] 0", " 중앙", "제공사 중앙값(Flopper)"),
        (ORN, "시장 지수", (0.50, 0.33, 0.66), "[5 2 1 2] 0", " 실거래", "실거래 지수(Ornn)")]
REFN = [r[0] for r in REFS]
WINDOW = (10, 11)   # KST 시 — 이 사이 첫 Pulse 회차(매일)
LIVE = common.ROOT / "knowledge" / "models" / "gpu_rental.csv"
WB = common.ROOT / "knowledge" / "models" / "gpu_rental_wayback.csv"
MOVERS = common.ROOT / "knowledge" / "models" / "gpu_rental_movers.json"   # 계열별 변동 성격(radar/gpu_movers.py)
OUT = common.ROOT / "radar" / "inbox" / "gpu_daily"   # 매일 그림(git 제외)
WB_FIELDS = ["date", "provider", "gpu", "config", "usd_per_gpu_hr", "node_usd_hr", "gpus_per_node", "snapshot", "source_url"]
CDX = "https://web.archive.org/cdx/search/cdx"
TARGETS = {"Nebius": "nebius.com/prices", "CoreWeave": "www.coreweave.com/pricing",
           "AWS": "b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/ec2/USD/current/ec2-ondemand-without-sec-sel/US%20East%20(N.%20Virginia)/Linux/index.json"}
READ_MAX = 200   # 2026-11-20 마스터 지시 "텔레그램 피드도 간략히 설명하도록 하라. 지금 설명은 너무 길다" — 풀이 1~2문장
START = "2026-01-01"   # 2026-11-19 마스터 지시 "2026년 YTD로 하나 그려놓고 여기서 매일 업데이트하며 추이를 이어가도록" — 해가 바뀌어도 이 날부터 잇는다


# ---------- 아카이브 역수집 ----------
def _wb_get(url, tries=3):
    for k in range(tries):
        try:
            b = common.http_get(url, timeout=90)
            return gzip.decompress(b) if b[:2] == b"\x1f\x8b" else b
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(30 * (k + 1))   # 아카이브는 빠른 연속 요청을 끊는다 — 물러섰다가 다시


def snapshots(prov, since):
    q = f"{CDX}?url={TARGETS[prov]}&from={since.replace('-', '')}&output=json&filter=statuscode:200&collapse=timestamp:8&fl=timestamp,original"
    d = json.loads(_wb_get(q))
    return [(t, o) for t, o in d[1:]]


def _cells(t):
    t = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", t)
    t = re.sub(r"(?s)<!--.*?-->", "", t)
    s = html.unescape(re.sub(r"<[^>]+>", "\x00", t))
    return [re.sub(r"\s+", " ", x).strip() for x in s.split("\x00") if x.strip()]


NUMC = re.compile(r"^[0-9][0-9,.\-]*(\^\d+)?$")
PRICE = re.compile(r"^(?:from )?\$\s?([0-9][0-9,]*\.?\d*)(?:\s*/\s*Hour)?$", re.I)


def _cell_rows(c, name_re, per_node):
    """옛 페이지 구조용 — 'GPU 이름 | 숫자 칸들 | $가격' 줄. per_node면 첫 숫자 칸 = GPU 수, 가격 ÷ GPU 수.
    숫자 칸 없이 바로 $가 오는 카드('as low as' 약정가)는 표가 아니라서 건너뛴다"""
    out = {}
    for i, x in enumerate(c):
        m = name_re.match(x)
        if not m or m.group(1) in out:
            continue
        nums, price, contact = [], None, False
        for y in c[i + 1:i + 10]:
            if y == x:
                continue
            if name_re.match(y) or y.startswith(("NVIDIA ", "AMD ")) or re.match(r"^\d+ × ", y):
                break
            if re.match(r"(?i)contact", y):
                contact = True
                break
            p = PRICE.match(y)
            if p:
                price = float(p.group(1).replace(",", ""))
                break
            if NUMC.match(y):
                nums.append(y)
        if not nums or (price is None and not contact):
            continue
        n = int(nums[0].split("^")[0].replace(",", "")) if per_node else 1
        out[m.group(1)] = {"gpu": m.group(1), "config": x, "usd_per_gpu_hr": round(price / n, 2) if price is not None and n else None,
                           "node_usd_hr": price if per_node else None, "gpus_per_node": n if per_node else None}
    return list(out.values())


NEB_NAME = re.compile(r"^(?:1 × |NVIDIA (?:HGX )?)(H100|H200|B200|B300)(?: SXM\d?| GPU)?$")
CW_NAME = re.compile(r"^NVIDIA (?:HGX )?(H100|H200|B200|B300)$")


def parse_snapshot(prov, raw):
    """스냅숏 본문 → [{gpu, config, usd_per_gpu_hr, node_usd_hr, gpus_per_node}] (온디맨드, 네 GPU만)"""
    if prov == "AWS":
        rows = gpu_rental.aws(raw)
    else:
        t = raw.decode("utf-8", "ignore")
        fn = gpu_rental.nebius if prov == "Nebius" else gpu_rental.coreweave
        rows = [r for r in fn(t) if not r["term"].startswith(("선점형", "스팟"))]
        ok = [r for r in rows if r["gpu"] in GPUS]
        if not ok:   # 옛 구조 — 칸 순서로 읽는다
            rows = _cell_rows(_cells(t), NEB_NAME if prov == "Nebius" else CW_NAME, prov == "CoreWeave")
    out = {}
    for r in rows:
        g = r["gpu"]
        cfg = r.get("config") or ""
        if g not in GPUS or re.search(r"PCIe|NVL|GH200|GB", cfg, re.I):
            continue
        out.setdefault(g, {k: r.get(k) for k in ("gpu", "config", "usd_per_gpu_hr", "node_usd_hr", "gpus_per_node")})
    return list(out.values())


def _wb_read():
    if not WB.exists():
        return []
    with WB.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _wb_write(rows):
    with WB.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=WB_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["provider"], r["gpu"], r["date"], r.get("snapshot") or "")))


def backfill_index(since="2026-01-01", pause=6.0):
    """Silicon Data 공개 지수 페이지(gpu_rental.SD_PAGES)의 아카이브 스냅숏 → 네 GPU 지수 헤드라인 값(이어받기).
    한 페이지에 자기 GPU 카드가 없고 다른 GPU 카드들이 있어(H100 페이지엔 H100 카드 없음) 두 페이지를 모두 읽는다"""
    st = common.load_state(STATE, {})
    done = set(st.get("wb_done") or [])
    rows, added = _wb_read(), 0
    for page in gpu_rental.SD_PAGES:
        orig = page.split("://", 1)[1]
        try:
            snaps = json.loads(_wb_get(f"{CDX}?url={orig}&from={since.replace('-', '')}&output=json&filter=statuscode:200&collapse=timestamp:8&fl=timestamp"))[1:]
        except Exception as e:
            print(f"[GPU Daily] 지수 스냅숏 목록 실패 {type(e).__name__}")
            continue
        time.sleep(pause)
        for (ts,) in snaps:
            k = f"SD|{orig}|{ts}"
            if k in done:
                continue
            url = f"https://web.archive.org/web/{ts}id_/{page}"
            try:
                got = gpu_rental.silicon_data({page: _wb_get(url).decode("utf-8", "ignore")})
            except Exception as e:
                print(f"[GPU Daily] 지수 {ts} 실패 {type(e).__name__}")
                time.sleep(pause)
                continue
            d = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
            got = [r for r in got if r["gpu"] in GPUS and r.get("usd_per_gpu_hr")]
            for r in got:
                rows.append({"date": d, "provider": IDX, "gpu": r["gpu"], "config": r["config"], "usd_per_gpu_hr": r["usd_per_gpu_hr"],
                             "snapshot": ts, "source_url": url})
                added += 1
            done.add(k)
            print(f"[GPU Daily] 지수 {d} " + ", ".join(f"{r['gpu']} {r['usd_per_gpu_hr']}" for r in got))
            st["wb_done"] = sorted(done)
            common.save_state(STATE, st)
            _wb_write(rows)
            time.sleep(pause)
    return added


def backfill_flopper():
    """Flopper 페이지에 든 제공사별 일별 온디맨드가 30일치 → 날짜별 중앙값을 아카이브 CSV에 채운다(이미 있는 날은 그대로).
    수집기는 매일 그날 값만 쌓으므로 놓친 날이 생기면 이걸 다시 돌려 메운다(2026-11-21)"""
    rows = _wb_read()
    have = {(r["provider"], r["gpu"], r["date"]) for r in rows}
    stamp = common.now_kst().strftime("%Y%m%d")
    added = 0
    for r in gpu_rental.flopper(history=True):
        k = (FLP, r["gpu"], r["date_obs"])
        if r["gpu"] not in GPUS or k in have:
            continue
        rows.append({"date": r["date_obs"], "provider": FLP, "gpu": r["gpu"], "config": r["config"], "usd_per_gpu_hr": r["usd_per_gpu_hr"],
                     "snapshot": f"flopper-{stamp}", "source_url": r["source_url"]})
        have.add(k)
        added += 1
    _wb_write(rows)
    return added


def backfill_ornn():
    """Ornn 공개 이력(GPU별 최근 3개월 일별) → 내부용 CSV(radar/inbox/gpu_ornn.csv, git 제외 — 이미 있는 날은 그대로). 놓친 날이 생기면 다시 돌린다(2026-11-21)"""
    have = {(r["provider"], r["gpu"], r["date"]) for r in gpu_rental.internal_rows()}
    now = common.iso(common.now_kst())
    new = [{**r, "date": r["date_obs"], "retrieved_at": now} for r in gpu_rental.ornn_history() if (ORN, r["gpu"], r["date_obs"]) not in have]
    gpu_rental.write_internal(new)
    return len(new)


def backfill(since="2025-12-01", pause=6.0, provs=None):
    """아카이브 스냅숏(하루 1개)을 읽어 gpu_rental_wayback.csv에 더한다. 이미 읽은 스냅숏은 건너뛴다(이어받기)"""
    st = common.load_state(STATE, {})
    done = set(st.get("wb_done") or [])
    rows = _wb_read()
    added = 0
    for prov in provs or PROVS:
        try:
            snaps = snapshots(prov, since)
        except Exception as e:
            print(f"[GPU Daily] {prov} 스냅숏 목록 실패 {type(e).__name__}")
            continue
        time.sleep(pause)
        for ts, orig in snaps:
            k = f"{prov}|{ts}"
            if k in done:
                continue
            url = f"https://web.archive.org/web/{ts}id_/{orig}"
            try:
                got = parse_snapshot(prov, _wb_get(url))
            except Exception as e:
                print(f"[GPU Daily] {prov} {ts} 실패 {type(e).__name__}")
                time.sleep(pause)
                continue
            d = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
            for r in got:
                rows.append({"date": d, "provider": prov, **r, "snapshot": ts, "source_url": url})
                added += 1
            done.add(k)
            print(f"[GPU Daily] {prov} {d} " + ", ".join(f"{r['gpu']} {r['usd_per_gpu_hr']}" for r in got))
            st["wb_done"] = sorted(done)
            common.save_state(STATE, st)
            with WB.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=WB_FIELDS, extrasaction="ignore")
                w.writeheader()
                w.writerows(sorted(rows, key=lambda r: (r["provider"], r["gpu"], r["date"])))
            time.sleep(pause)
    return added


PL = "https://pricing.us-east-1.amazonaws.com"


def aws_pricelist(months=("2026-01", "2026-03", "2026-05", "2026-07"), dry=False):
    """AWS 공식 가격표 API(Price List, 공개·키 없음)의 월별 판으로 AWS 이력을 채운다 — 아카이브에 AWS 가격 JSON은 2026-09부터만 있다.
    판마다 미국 동부 EC2 CSV(약 300MB)를 흘려 읽으며 네 인스턴스 온디맨드 리눅스 줄만 뽑는다(파일은 저장하지 않는다).
    관측일 = 판 게시일(버전 id 날짜)"""
    import urllib.request
    idx = json.loads(common.http_get(f"{PL}/offers/v1.0/aws/AmazonEC2/index.json", timeout=60))["versions"]
    want = {it: g for it, g in gpu_rental.AWS_TYPES.items() if g in GPUS}
    st = common.load_state(STATE, {})
    done = set(st.get("wb_done") or [])
    rows, added = _wb_read(), 0
    for ver, v in sorted(idx.items()):
        if v["versionEffectiveBeginDate"][:7] not in months or f"AWSPL|{ver}" in done:
            continue
        url = f"{PL}/offers/v1.0/aws/AmazonEC2/{ver}/us-east-1/index.csv"
        if dry:
            print(url)
            continue
        req = urllib.request.Request(url, headers={"User-Agent": common.UA})
        head, got = None, {}
        with urllib.request.urlopen(req, timeout=120) as r:
            for raw in r:
                line = raw.decode("utf-8", "ignore")
                if head is None:
                    if line.startswith('"SKU"'):
                        head = next(csv.reader([line]))
                    continue
                if "48xlarge" not in line or '"OnDemand"' not in line or not any(f'"{it}"' in line for it in want):
                    continue
                c = dict(zip(head, next(csv.reader([line]))))
                if (c.get("TermType") == "OnDemand" and c.get("Operating System") == "Linux" and c.get("Tenancy") == "Shared" and c.get("Pre Installed S/W") == "NA"
                        and c.get("CapacityStatus") == "Used" and c.get("Unit") == "Hrs" and c.get("Instance Type") in want
                        and "BoxUsage" in (c.get("usageType") or c.get("Usage Type") or "")
                        and (c.get("MarketOption") or "OnDemand") == "OnDemand" and c.get("License Model") in (None, "", "No License required")):
                    p = float(c["PricePerUnit"])
                    if p > 0:   # 0원 줄(용량 예약 등 다른 시장 옵션)은 뺀다
                        got.setdefault(c["Instance Type"], set()).add(p)
        for k, v in got.items():
            if len(v) > 1:
                print(f"[GPU Daily] {ver} {k} 후보 여럿 {sorted(v)} — 최저값")
        got = {k: min(v) for k, v in got.items()}
        d = f"{ver[:4]}-{ver[4:6]}-{ver[6:8]}"
        for it, p in got.items():
            rows.append({"date": d, "provider": "AWS", "gpu": want[it], "config": it, "usd_per_gpu_hr": round(p / 8, 2), "node_usd_hr": round(p, 4),
                         "gpus_per_node": 8, "snapshot": f"pricelist:{ver}", "source_url": url})
            added += 1
        print(f"[GPU Daily] AWS 가격표 판 {ver} → " + ", ".join(f"{want[k]} {v / 8:.2f}" for k, v in got.items()))
        done.add(f"AWSPL|{ver}")
        st["wb_done"] = sorted(done)
        common.save_state(STATE, st)
        with WB.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=WB_FIELDS, extrasaction="ignore")
            w.writeheader()
            w.writerows(sorted(rows, key=lambda r: (r["provider"], r["gpu"], r["date"])))
    return added


# ---------- 시계열 ----------
def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def observations():
    """(제공사, GPU) → {날짜: 가격 또는 None(문의)}. 직접 수집값이 같은 날 아카이브값보다 우선.
    (IDX, GPU) = Silicon Data 시장 지수(참고선) — 같은 날 여러 번 읽었으면 그날 마지막 값"""
    obs = {(p, g): {} for p in PROVS + REFN for g in GPUS}
    for r in _wb_read():
        k = (r["provider"], r["gpu"])
        if k in obs:
            obs[k][r["date"]] = _num(r["usd_per_gpu_hr"])
    if LIVE.exists():
        with LIVE.open(encoding="utf-8", newline="") as f:
            for r in list(csv.DictReader(f)) + gpu_rental.internal_rows():   # 내부용(Ornn)은 git 제외 CSV에서
                k = (r["provider"], r["gpu"])
                if k not in obs:
                    continue
                if r["provider"] in REFN:
                    if r["term"].startswith(dict((x[0], x[1]) for x in REFS)[r["provider"]]) and _num(r["usd_per_gpu_hr"]) is not None:
                        obs[k][r["date"]] = _num(r["usd_per_gpu_hr"])
                    continue
                if not r["term"].startswith("온디맨드") or re.search(r"PCIe|NVL|GH200|GB", r["config"], re.I):
                    continue
                obs[k][r["date"]] = _num(r["usd_per_gpu_hr"])
    for g in GPUS:
        for n in REFN:
            obs[(n, g)] = index_clean(obs[(n, g)])
    return obs


def index_clean(o, lo=0.6, hi=1.6):
    """시장 지수 이상값 제거 — 아카이브 옛 스냅숏에 자리표시 값(2026-08-12~13 모든 카드 $68.0)과 이름표가 어긋난 값(07-28 H100 $7.17,
    앞뒤 2.6~3.1)이 있다. 원자료(csv)는 그대로 두고, 그 GPU 시리즈 중앙값의 lo~hi배 밖 값만 그림·요약에서 뺀다"""
    vs = sorted(v for v in o.values() if v is not None)
    if len(vs) < 5:
        return o
    med = vs[len(vs) // 2]
    return {d: v for d, v in o.items() if v is not None and lo * med <= v <= hi * med}


def series(obs, since, until):
    """계단선 — 시작일 이전 마지막 관측값을 시작일 값으로 잇는다. 값 없는(문의) 관측은 선을 끊는다"""
    out = {}
    for k, o in obs.items():
        ds = sorted(o)
        before = [d for d in ds if d < since]
        pts = [(since, o[before[-1]])] if before else []
        pts += [(d, o[d]) for d in ds if since <= d <= until]
        if not any(v is not None for _, v in pts):
            continue
        steps, last = [], None   # 값이 바뀐 구간(직전 관측일 ~ 바뀐 관측일)
        prev_d = None
        for d, v in pts:
            if v is not None and last is not None and abs(v - last) >= 0.005:
                steps.append({"from": prev_d, "to": d, "old": last, "new": v, "pct": (v / last - 1) * 100})
            if v is not None:
                last, prev_d = v, d
        vals = [(d, v) for d, v in pts if v is not None]
        out[k] = {"points": pts, "observed": [d for d in ds if since <= d <= until], "first": vals[0], "last": vals[-1],
                  "steps": steps, "chg": (vals[-1][1] / vals[0][1] - 1) * 100 if vals[0][1] else None}
    return out


def value_at(s, d):
    v = None
    for x, y in s["points"]:
        if x <= d and y is not None:
            v = y
    return v


# ---------- 그림(PyMuPDF — 새 패키지 없이) ----------
# 범주 색 = 고정 순서 첫 세 칸(파랑·주황·청록, dataviz 기본 팔레트 — 세 칸까지 전 쌍 색각 검증 통과로 문서화). 글자는 잉크색.
COL = {"Nebius": (0.165, 0.471, 0.839), "CoreWeave": (0.922, 0.408, 0.204), "AWS": (0.106, 0.686, 0.478)}
IDXC = REFS[0][2]   # 시장 지수 참고선 색(옛 이름 — REFS가 원본)
INK, INK2, MUTED, GRID, SURF = (0.043, 0.043, 0.043), (0.322, 0.318, 0.306), (0.537, 0.529, 0.506), (0.882, 0.878, 0.851), (0.988, 0.988, 0.984)


def _d(s):
    return date.fromisoformat(s) if isinstance(s, str) else s


def _panel(page, box, g, S, d0, d1):
    from memory_spot import _nice, _txt
    x0, y0, x1, y1 = box
    mine = {p: S[(p, g)] for p in PROVS if (p, g) in S}
    refs = [(r, S[(r[0], g)]) for r in REFS if (r[0], g) in S]
    vals = [v for s in list(mine.values()) + [x for _, x in refs] for _, v in s["points"] if v is not None]
    hi = max(vals) if vals else 1
    step = _nice(hi / 4)
    top = math.ceil(hi * 1.08 / step) * step
    span = max((d1 - d0).days, 1)
    X = lambda d: x0 + (x1 - x0) * (_d(d) - d0).days / span   # noqa: E731
    Y = lambda v: y1 - (y1 - y0) * v / top                     # noqa: E731
    _txt(page, (x0, y0 - 12), g, 12, INK)
    v = 0.0
    while v <= top + 1e-9:
        page.draw_line((x0, Y(v)), (x1, Y(v)), color=GRID, width=0.5)
        _txt(page, (x0 - 5, Y(v) + 3), f"${v:,.0f}", 7, MUTED, right=True)
        v += step
    m = date(d0.year, d0.month, 1)
    while m <= d1:
        every = 1 if span < 200 else (2 if span < 550 else 3)
        if m >= d0 and (m.month - 1) % every == 0:
            _txt(page, (X(m) - 6, y1 + 11), f"{m.year % 100}.1" if m.month == 1 and m.year != d0.year else f"{m.month}월", 7, MUTED)
        m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    page.draw_line((x0, y1), (x1, y1), color=MUTED, width=0.6)
    ends, missing = [], []
    for (name, _, col, dash, _, _), idx in refs:   # 참고선(2026-11-21) — 매일 움직이는 시장 값. 제공사 선 아래에 깐다
        sg = [(X(d), Y(v)) for d, v in idx["points"] if v is not None and d >= d0.isoformat()]
        if len(sg) > 1:
            page.draw_polyline(sg, color=col, width=1.3, dashes=dash)
        ends.append([Y(idx["last"][1]), name, idx["last"][1]])
    for p in PROVS:
        s = mine.get(p)
        if not s:
            missing.append(p)
            continue
        segs, cur, last, gaps = [], [], None, []   # 계단선 — 값 없는(문의) 관측에서 끊는다
        pts = s["points"] + ([(d1.isoformat(), s["points"][-1][1])] if s["points"][-1][1] is not None else [])
        for d, v in pts:
            if v is None:
                if cur:
                    segs.append(cur)
                cur, last = [], None
                continue
            if last is not None and abs(v - last) >= 0.005:   # 두 관측 사이 어느 날 바뀜 — 점선 사선(바뀐 날을 지어내지 않는다)
                gaps.append((cur[-1], (X(d), Y(v))))
                segs.append(cur)
                cur = [(X(d), Y(v))]
            else:
                cur.append((X(d), Y(v)))
            last = v
        if cur:
            segs.append(cur)
        for sg in segs:
            if len(sg) > 1:
                page.draw_polyline(sg, color=SURF, width=3.6)   # 겹치는 선 사이 바탕색 테두리
                page.draw_polyline(sg, color=COL[p], width=1.8)
        for a, b in gaps:
            page.draw_line(a, b, color=COL[p], width=1.3, dashes="[2 2] 0")
        for st in s["steps"]:   # 값이 바뀐 것을 처음 본 관측일
            page.draw_circle((X(st["to"]), Y(st["new"])), 2.6, color=SURF, fill=COL[p], width=0.8)
        ends.append([Y(s["last"][1]), p, s["last"][1]])
    ends.sort()
    for i in range(1, len(ends)):   # 끝 이름표 겹침 풀기(최소 10pt 간격)
        ends[i][0] = max(ends[i][0], ends[i - 1][0] + 10)
    for y, p, v in ends:
        ref = next((r for r in REFS if r[0] == p), None)
        c = ref[2] if ref else COL[p]
        page.draw_circle((x1 + 6, y - 2.5), 2.6, color=c, fill=c)
        _txt(page, (x1 + 11, y + 0.5), f"${v:,.2f}" + (ref[4] if ref else ""), 7.5, INK2 if ref else INK)
    if missing:
        _txt(page, (x0 + 4, y0 + 10), " · ".join(missing) + " 공개 정가 없음(문의)", 7, INK2)


def chart(since=None, until=None, path=None):
    """→ (png 경로, 요약 dict)"""
    import pymupdf
    from memory_spot import _txt
    now = common.now_kst()
    since = since or START
    until = until or now.date().isoformat()
    S = series(observations(), since, until)
    if not S:
        raise SystemExit("[GPU Daily] 자료 없음 — gpu_rental.csv·--backfill 확인")
    d0, d1 = _d(since), _d(until)
    doc = pymupdf.open()
    page = doc.new_page(width=760, height=744)
    page.draw_rect(page.rect, color=None, fill=SURF)
    _txt(page, (36, 34), f"GPU 렌털비 추이 — 온디맨드 정가 $/GPU·시 ({_ymd(since)}~)", 15, INK)
    _txt(page, (36, 52), f"기준 {until} · 실선 = 정가(다음 관측까지 유지), 점선 사선 = 두 관측 사이 어느 날 바뀜, 회색·보라 점선 = 시장 참고값(정가와 정의가 다름)", 8.5, INK2)
    x = 36
    for p in PROVS:   # 범례(세 계열 — 끝 이름표와 함께)
        page.draw_line((x, 72), (x + 18, 72), color=COL[p], width=2)
        _txt(page, (x + 23, 75), p, 9, INK)
        x += 84
    for name, _, col, dash, _, leg in REFS:   # 참고선 범례 — 같은 줄 이어서(둘째 줄은 칸 제목과 겹친다)
        if any(k[0] == name for k in S):
            page.draw_line((x, 72), (x + 18, 72), color=col, width=1.4, dashes=dash)
            _txt(page, (x + 23, 75), leg, 9, INK2)
            x += 23 + sum(9.2 if ord(ch) > 0x1100 else 5.0 for ch in leg) + 16   # 글자 폭 어림 — 범례가 오른쪽 끝을 넘지 않게
    boxes = [(70, 110, 320, 370), (440, 110, 690, 370), (70, 430, 320, 680), (440, 430, 690, 680)]
    for g, box in zip(GPUS, boxes):
        _panel(page, box, g, S, d0, d1)
    _txt(page, (36, 704), "자료: Nebius·CoreWeave 공개 가격표, AWS EC2 온디맨드 가격표(미국 동부·리눅스, 8 GPU 인스턴스÷8). "
         "이전 구간은 인터넷 아카이브 스냅숏·AWS 가격표 API 월별 판.", 7, MUTED)
    _txt(page, (36, 715), "시장 지수: Silicon Data 공개 페이지 헤드라인 값 인용(거래 가격 기반 지수, 2026-07-28 이전은 아카이브 없음). 정가와 정의가 달라 직접 비교하지 않는다.", 7, MUTED)
    _txt(page, (36, 737), "실거래 지수: Ornn Compute Price Index(실제 임대 거래 정산, 미 동부 자정 기준 일 1회) — 개인 참고용, 재배포하지 않는다.", 7, MUTED)
    _txt(page, (36, 726), "제공사 중앙값: Flopper.io GPU별 가격 페이지의 제공사별 일별 최저 온디맨드가(15~31곳)의 그날 중앙값 — 정가 모음이며 거래가가 아니다.", 7, MUTED)
    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(path or OUT / f"gpu_trend_{until.replace('-', '')}.png")
    page.get_pixmap(dpi=150).save(str(path))
    return path, summary(S, since, until, str(path))


def summary(S, since, until, png=""):
    out = {"since": since, "until": until, "png": png, "gpus": []}
    d7 = (_d(until) - timedelta(days=7)).isoformat()
    for g in GPUS:
        row = {"gpu": g, "prov": {}}
        for p in PROVS:
            s = S.get((p, g))
            if not s:
                continue
            last = s["last"]
            w = value_at(s, d7)
            row["prov"][p] = {"usd": last[1], "first": list(s["first"]), "ytd": s["chg"], "1w": (last[1] / w - 1) * 100 if w else None,
                              "steps": [{**x, "pct": round(x["pct"], 1)} for x in s["steps"]]}
        out["gpus"].append(row)
    out["refs"] = {}
    for name in REFN:   # 참고선(2026-11-21) — 지금 값·1주 변화·4주 변화
        for g in GPUS:
            s = S.get((name, g))
            if not s:
                continue
            last = s["last"]
            w, m = value_at(s, d7), value_at(s, (_d(until) - timedelta(days=28)).isoformat())
            out["refs"].setdefault(name, {})[g] = {"usd": last[1], "day": last[0], "1w": (last[1] / w - 1) * 100 if w else None,
                                                   "4w": (last[1] / m - 1) * 100 if m else None, "first": list(s["first"])}
    out["index"] = out["refs"].get(IDX, {})
    try:   # 매일 움직여야 할 원천이 멈췄는지(radar/gpu_movers.py, 2026-11-21) — 멈춘 지수를 '평평한 시장'으로 읽지 않게
        mv = json.loads(MOVERS.read_text(encoding="utf-8"))
        out["stale"] = (mv.get("stale") or []) if str(mv.get("as_of", ""))[:10] >= (_d(until) - timedelta(days=1)).isoformat() else []
    except Exception:
        out["stale"] = []
    return out


def _ymd(s):
    return f"{s[:4]}.{int(s[5:7])}.{int(s[8:10])}"


def _md(s):
    return f"{int(s[5:7])}/{int(s[8:10])}" if s else "?"


SHORT = {"Nebius": "Nebius", "CoreWeave": "CW", "AWS": "AWS"}


def caption(summ, read=""):
    """간략 양식(마스터 지시 2026-11-20 "텔레그램 피드도 간략히 설명하도록 하라. 지금 설명은 너무 길다") —
    머리 1줄 · GPU별 세 곳 가격 1줄씩 · 가장 최근 가격 변경 1줄(같은 제공사·같은 구간은 한 줄로 묶음) · 풀이 1~2문장. 자세한 계단은 그림에"""
    L = [f"[Chiip Pulse] GPU 렌털비 {_md(summ['until'])} · 온디맨드 $/GPU·시 ({' · '.join(SHORT[p] for p in PROVS)})"]
    for r in summ["gpus"]:
        L.append(f"{r['gpu']}  " + " · ".join(f"{r['prov'][p]['usd']:.2f}" if p in r["prov"] else "문의" for p in PROVS))
    ev = {}
    for r in summ["gpus"]:
        for p, c in r["prov"].items():
            for x in c["steps"]:
                ev.setdefault((p, x["from"], x["to"]), []).append(x["pct"])
    if ev:
        (p, a, b), pcts = max(ev.items(), key=lambda kv: kv[0][2])
        rng = f"{min(pcts):+.0f}%" if round(min(pcts)) == round(max(pcts)) else f"{min(pcts):+.0f}~{max(pcts):.0f}%"
        L.append(f"최근 변경: {p} {len(pcts)}종 {rng}({_md(a)}~{_md(b)})")
    refs = summ.get("refs") or ({IDX: summ["index"]} if summ.get("index") else {})
    for name, head in ((IDX, "시장 지수"), (ORN, "실거래 지수(Ornn)"), (FLP, "제공사 중앙값")):   # 참고값 한 줄씩(2026-11-21) — 정가가 평평해도 시장 움직임이 보이게
        ix = refs.get(name) or {}
        if ix:
            L.append(f"{head} " + " · ".join(f"{g} {x['usd']:.2f}" + (f"({x['1w']:+.1f}%)" if x.get("1w") is not None else "") for g, x in ix.items()) + " · 1주")
    for s in summ.get("stale") or []:
        L.append(f"주의: {s} — 원천 갱신 멈춤 의심")
    flat = [SHORT[p] for p in PROVS if any(p in r["prov"] for r in summ["gpus"]) and not any(r["prov"].get(p, {}).get("steps") for r in summ["gpus"])]
    if flat:
        L.append(f"{'·'.join(flat)} 연초 이후 정가 변동 없음")
    if read:
        L += ["", read.strip()]
    return "\n".join(L)


def status(now=None):
    """Pulse 관문 — 매일 10~11시 KST, 하루 1회(주말 포함)"""
    now = now or common.now_kst()
    st = common.load_state(STATE, {})
    today = now.date().isoformat()
    if not (WINDOW[0] <= now.hour < WINDOW[1]) or st.get("sent") == today:
        return {"due": False}
    try:
        png, summ = chart(until=today)
    except (Exception, SystemExit) as e:
        return {"due": False, "error": f"{type(e).__name__}: {str(e)[:120]}"}
    return {"due": True, "png": str(png), "summary": summ, "preview": caption(summ)}


def send(read=""):
    import notify
    png, summ = chart()
    cap = caption(summ, read)
    # 그림과 풀이는 한 통(사진 설명)으로만 — 따로 글을 보내지 않는다(마스터 지시 2026-11-20 "풀이 피드를 따로 내지 말고 그래프 제공하는 피드에 같이 설명을 넣어라")
    base = caption(summ)
    room = 1000 - len(base) - 2
    cap = caption(summ, read if len(read.strip()) <= room else read.strip()[:max(room - 1, 0)].rsplit(' ', 1)[0] + '…') if read and room > 20 else base
    ok = notify.send_photo(png, cap[:1000], "P2")
    if ok:
        st = common.load_state(STATE, {})
        st["sent"] = common.now_kst().date().isoformat()
        common.save_state(STATE, st)
    return ok


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["--backfill-ornn"]:
        print(f"[GPU Daily] Ornn 지수 {backfill_ornn()}행")
    elif argv[:1] == ["--backfill-flopper"]:
        print(f"[GPU Daily] Flopper 중앙값 {backfill_flopper()}행")
    elif argv[:1] == ["--backfill-index"]:
        print(f"[GPU Daily] 지수 아카이브 {backfill_index(argv[1] if len(argv) > 1 else '2026-01-01')}행")
    elif argv[:1] == ["--backfill"]:
        print(f"[GPU Daily] 아카이브 {backfill(argv[1] if len(argv) > 1 else '2025-12-01')}행")
    elif argv[:1] == ["--chart"]:
        png, summ = chart(argv[1] if len(argv) > 1 else None)
        print(caption(summ))
        print(png)
    elif argv[:1] == ["--send"]:
        d = json.loads(Path(argv[1]).read_text(encoding="utf-8")) if len(argv) > 1 else {}
        read = (d.get("read") or "").strip()
        if len(read) > READ_MAX:
            raise SystemExit(f"read {len(read)}자 — {READ_MAX}자 이내")
        if re.search(r"(사라[.!\s]|사라$|팔아라|매수하라|매도하라|비중 확대|비중 축소)", read):
            raise SystemExit("GPU Daily 관문 — 매매 지시 표현")
        print("[GPU Daily] 발송" if send(read) else "[GPU Daily] 발송 실패")
    else:
        print(json.dumps(status(), ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
