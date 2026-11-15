async () => {
  // SPAC 과거 표본 종결 뒤 수익(scripts/tenbagger/spac_history.py, 2026-11-04 4단계 → 2026-11-15 재계산 ADR-044).
  // LIST = `py scripts/tenbagger/spac_history.py keys --limit 48 --offset N` 출력([cik, 종결일, [키 후보…]] — Fiscal CIK 일치 키가 맨 앞).
  // 키마다 split-adjusted 종가를 받아 종결 8-K 날짜 이후 첫 종가를 기준으로 126·252·504거래일 수익, 504일 안 최고 배수, 마지막 시세(상장폐지면 그 날)를 낸다.
  // 분할 전 원래 종결가(base_px) = 기준일 조정 종가 × 기준일 뒤 분할 비율의 곱(company_stock_splits rate = 옛 주식 1주당 새 주식 수) — $10 기준 수익에 쓴다.
  // 같은 주에 분할이 두 번 잡히면(Workhorse 2024-06-14·06-17) 발표일 없는 쪽을 뺀다. 종결 뒤 20거래일 시세가 없는 키(옛 스팩 티커 등)는 건너뛴다.
  // 출력 행: [cik, key, listing, base_date, base_px, last_date, term_r, r6m, r12m, r24m, max24m, now_x, n_splits] · 시세 없음은 [cik] · 시간이 모자라 못 본 것은 pending.
  const LIST = [];
  const T0 = Date.now(), BUDGET = 48000;
  const out = [], pending = [];
  const clean = sp => (sp || []).filter(x => x && x.rate > 0 && x.exDate).filter((x, i, a) => !(!x.announceDate && a.some(y => y !== x && y.announceDate && Math.abs(new Date(y.exDate) - new Date(x.exDate)) <= 7 * 864e5)));
  const one = async ([cik, d, keys]) => {
    for (const k of keys) {
      let p; try { p = await codemode.company_stock_prices({ companyKey: k }); } catch (e) { continue; }
      const s = (p.prices || []).filter(x => x.closePrice != null && x.closePrice > 0).map(x => [x.date, x.closePrice]).sort((a, b) => a[0] < b[0] ? -1 : 1);
      const i0 = s.findIndex(x => x[0] >= d);
      if (i0 < 0 || s.length - i0 < 21) continue;
      let sp = []; try { sp = clean(await codemode.company_stock_splits({ companyKey: k })); } catch (e) {}
      const b = s[i0][1], fac = sp.filter(x => x.exDate > s[i0][0]).reduce((f, x) => f * x.rate, 1);
      const at = h => s[i0 + h] ? +(s[i0 + h][1] / b - 1).toFixed(4) : null;
      const win = s.slice(i0, i0 + 505).map(x => x[1] / b), last = s[s.length - 1];
      out.push([cik, k, p.tradingStatus || "", s[i0][0], +(b * fac).toPrecision(5), last[0], +(last[1] / b - 1).toFixed(4), at(126), at(252), at(504), +Math.max(...win).toFixed(3), +(last[1] / b).toFixed(4), sp.length]);
      return;
    }
    out.push([cik]);
  };
  const q = LIST.slice();
  const worker = async () => { while (q.length) { if (Date.now() - T0 > BUDGET) { pending.push(...q.splice(0).map(x => x[0])); return; } await one(q.shift()); } };
  await Promise.all(Array.from({ length: 6 }, worker));
  console.log(JSON.stringify({ out, pending }));
}
