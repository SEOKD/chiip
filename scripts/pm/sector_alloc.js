async () => {
  // Portfolio 섹터 배분 재료(scripts/pm/sector_alloc.py, 마스터 지시 2026-11-04). __KEYS__ = `py scripts/pm/sector_alloc.py --code <몇째 묶음>`이 채운다.
  // 종목마다: 시가총액, 21·126·252거래일 수익(12-1·6-1 모멘텀), 200일선 위 여부, EV/매출의 3년 백분위(낮을수록 싸다), 30일 EPS 추정 변화.
  // 출력(압축): [[key, mcap_b, r21, r126, r252, above200(0/1), evs_pct3y, rev30], …] → 파일 → `py scripts/pm/sector_alloc.py --put <파일>`
  const keys = __KEYS__;
  const r4 = x => x == null || !isFinite(x) ? null : +x.toFixed(4);
  const one = async k => {
    const [px, z, ev, mc] = await Promise.all([
      codemode.company_stock_prices({ companyKey: k }),
      codemode.company_analyst_estimates({ companyKey: k, history: true }).catch(() => ({ history: [] })),
      codemode.company_daily_ratios({ ratioId: "ratio_ev_to_sales", companyKey: k }).catch(() => []),
      codemode.company_daily_ratios({ ratioId: "calculated_market_cap", companyKey: k }).catch(() => [])]);
    const c = (px.prices || []).filter(x => x.closePrice != null).sort((a, b) => a.date < b.date ? -1 : 1).map(x => x.closePrice);
    const L = c.length, last = c[L - 1], back = n => L > n ? c[L - 1 - n] : null;
    const ma200 = L >= 200 ? c.slice(-200).reduce((s, v) => s + v, 0) / 200 : null;
    const e = (Array.isArray(ev) ? ev : []).slice().sort((a, b) => a.date < b.date ? -1 : 1).map(x => x.ratio).filter(x => x != null);
    const e3 = e.slice(-756), now = e3[e3.length - 1];
    const pct = e3.length > 60 ? e3.filter(x => x <= now).length / e3.length : null;
    const cut = new Date(Date.now() - 30 * 864e5).toISOString().slice(0, 10), far = new Date(Date.now() + 180 * 864e5).toISOString().slice(0, 10);
    const hist = (z.history || []).filter(h => h.metricId === "analyst_eps" && h.periodType === "Annual" && h.reportDate > far);
    const fy = hist.map(h => h.reportDate).sort()[0];
    const fh = hist.filter(h => h.reportDate === fy).sort((a, b) => String(a.asOf || "") < String(b.asOf || "") ? -1 : 1);
    const n0 = fh[fh.length - 1], t0 = fh.filter(h => !h.asOf || h.asOf <= cut).slice(-1)[0];
    const m = (Array.isArray(mc) ? mc : []).slice().sort((a, b) => a.date < b.date ? -1 : 1);
    return [k, r4((m[m.length - 1] || {}).ratio / 1e9), r4(back(21) ? last / back(21) - 1 : null), r4(back(126) ? last / back(126) - 1 : null),
            r4(back(252) ? last / back(252) - 1 : null), ma200 == null ? null : (last > ma200 ? 1 : 0), r4(pct),
            r4(n0 && t0 && t0.mean ? n0.mean / t0.mean - 1 : null)];
  };
  const rows = [], errors = [];
  for (let i = 0; i < keys.length; i += 4) {
    const got = await Promise.all(keys.slice(i, i + 4).map(k => one(k).catch(e => { errors.push(k + ": " + String(e.message || e).slice(0, 60)); return null; })));
    rows.push(...got.filter(Boolean));
  }
  console.log(JSON.stringify({ rows, errors }));
}
