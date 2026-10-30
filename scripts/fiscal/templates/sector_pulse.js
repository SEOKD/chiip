async () => {
  // 섹터 바스켓 종목의 주가·배수·EPS 추정 변화 — Chiip Portfolio 시장 국면(마스터 지시 2026-10-30). radar/market_regime.py --sector-code가 종목 키를 채운다.
  // 출력 → 파일 저장 → py radar/market_regime.py --sector-put <파일>
  const keys = __KEYS__;
  const med = a => { const s = a.slice().sort((x, y) => x - y); return s.length ? s[Math.floor(s.length / 2)] : null; };
  const back = (a, n) => a.length > n ? a[a.length - 1 - n] : null;
  const one = async k => {
    const [px, z, ev] = await Promise.all([
      codemode.company_stock_prices({ companyKey: k }),
      codemode.company_analyst_estimates({ companyKey: k, history: true }).catch(() => ({ data: [], history: [] })),
      codemode.company_daily_ratios({ ratioId: "ratio_ev_to_sales", companyKey: k }).catch(() => [])]);
    let p = (px.prices || []).filter(x => x.closePrice != null).sort((a, b) => a.date < b.date ? -1 : 1);
    if (p.length > 21 && (p[p.length - 1].volume || 0) < 0.01 * med(p.slice(-21, -1).map(x => x.volume || 0))) p = p.slice(0, -1);   // 미확정 봉 제외
    const c = p.map(x => x.closePrice), last = c[c.length - 1];
    const ret = n => back(c, n) ? last / back(c, n) - 1 : null;
    const ma50 = c.slice(-50).reduce((s, v) => s + v, 0) / Math.min(50, c.length);
    const high = Math.max(...c.slice(-252));
    const r = (Array.isArray(ev) ? ev : []).slice().sort((a, b) => a.date < b.date ? -1 : 1).map(x => x.ratio);
    const cut = new Date(Date.now() - 30 * 864e5).toISOString().slice(0, 10), far = new Date(Date.now() + 180 * 864e5).toISOString().slice(0, 10);
    const hist = (z.history || []).filter(h => h.metricId === "analyst_eps" && h.periodType === "Annual" && h.reportDate > far);
    const fy = hist.map(h => h.reportDate).sort()[0];
    const fh = hist.filter(h => h.reportDate === fy).sort((a, b) => String(a.asOf || "") < String(b.asOf || "") ? -1 : 1);
    const now = fh[fh.length - 1], then = fh.filter(h => !h.asOf || h.asOf <= cut).slice(-1)[0];
    return { key: k, date: p[p.length - 1].date, close: last, r1: ret(1), r5: ret(5), r20: ret(20), r60: ret(60), above50: last > ma50, dd: last / high - 1,
      evs: r[r.length - 1] ?? null, evs_chg20: r.length > 21 ? r[r.length - 1] / r[r.length - 21] - 1 : null,
      fy, eps: now ? now.mean : null, rev30: now && then && then.mean ? now.mean / then.mean - 1 : null, n: now ? now.numEstimates : null };
  };
  const rows = [], errors = [];
  for (let i = 0; i < keys.length; i += 3) {
    const got = await Promise.all(keys.slice(i, i + 3).map(k => one(k).catch(e => { errors.push(k + ": " + String(e.message || e).slice(0, 80)); return null; })));
    rows.push(...got.filter(Boolean));
  }
  console.log(JSON.stringify({ rows, errors }));
}
