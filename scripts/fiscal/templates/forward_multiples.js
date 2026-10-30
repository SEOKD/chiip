async () => {
  // Fwd 1Y 멀티플 묶음 — 텐배거 리포트 멀티플 절의 재료(마스터 지시 2026-10-30 "Fwd 1Y P/E나 Fwd 1Y EV/EBITDA 등 이익 지표로. Fwd 1Y 멀티플은 Fiscal.ai에서 우선적으로").
  // 순서: Fiscal 자체 Forward 배수(ratio_forward_*, 분모 = 다음 4개 분기 추정) → 없으면 Street Forward(ratio_street_forward_*).
  // Fwd 2Y·3Y(마스터 지시 2026-10-30 "Fwd 1Y, Fwd 2Y, Fwd 3Y 세 분류"): Fiscal에 배수가 없어 company_estimates의 5~8번째·9~12번째 분기 추정으로 분모를 만든다 — 배수 계산은 adapter.put_forward.
  // 추정은 9~10개 분기까지만 있어 Fwd 3Y의 모자란 분기(최대 3개)는 전년 같은 분기 × (1 + 마지막 회계연도 추정 성장률, −30~+50%로 제한)로 연장하고 ext에 개수를 남긴다.
  // 과거 레인지는 일별 Forward 배수가 없어 월말 가격 ÷ 그 시점 다음 4개 분기 추정 합으로 계산한다(추정 변경 이력).
  // 출력 → 파일 저장 → py scripts/fiscal/adapter.py --forward-multiples <id> <파일> → datapack multiples_now·forward·peers·history.
  // Street 값·추정 이력은 Zacks 수치 — 데이터 묶음에 표기 의무("Data provided by Zacks Investment Research, Inc., www.zacksdata.com"). 리포트 본문에는 제공처를 쓰지 않는다.
  const k = "__KEY__";
  const peers = __PEERS__;   // ["NASDAQ_ICHR", …] 동종사 회사 키
  const OWN = { pe: "ratio_forward_price_to_earnings", ev_ebitda: "ratio_forward_ev_to_ebitda" };
  const STREET = { pe: "ratio_street_forward_price_to_earnings", ev_ebitda: "ratio_street_forward_ev_to_ebitda" };
  const pos = v => (typeof v === "number" && v > 0 ? Math.round(v * 100) / 100 : null);
  const latest = async key => {
    const r = await codemode.company_ratios({ companyKey: key, periodType: "latest", ratioId: [...Object.values(OWN), ...Object.values(STREET)].join(",") }).catch(() => null);
    const v = ((r && r.data) || []).slice(-1)[0];
    const m = (v && v.metricValues) || {};
    const pick = f => (pos(m[OWN[f]]) != null ? [pos(m[OWN[f]]), "fiscal"] : pos(m[STREET[f]]) != null ? [pos(m[STREET[f]]), "street"] : [null, null]);
    const [pe, peSrc] = pick("pe");
    const [ev, evSrc] = pick("ev_ebitda");
    return { pe_fwd: pe, ev_ebitda_fwd: ev, src: { pe_fwd: peSrc, ev_ebitda_fwd: evSrc } };
  };
  const target = await latest(k);

  // 다음 4개 분기 추정 — 주요 지표 판별 재료(가이던스를 내는 지표, 감가상각 비중)와 펀더멘털 내재 멀티플의 선행 이익률·성장
  const ntmOf = async key => {
    const fe = await codemode.company_estimates({ companyKey: key }).catch(() => ({ data: [] }));
    const qs = (fe.data || []).filter(r => r.periodType === "Quarterly").sort((a, b) => (a.reportDate < b.reportDate ? -1 : 1));
    const unreported = r => (r.metricsValues.revenue || {}).actual == null;
    const next = qs.filter(unreported);
    const annual = (fe.data || []).filter(r => r.periodType === "Annual" && unreported(r)).sort((a, b) => (a.fiscalYear < b.fiscalYear ? -1 : 1));
    const val = (r, id) => (r.metricsValues[id] || {}).mean;
    const growth = id => {
      const v = annual.map(r => val(r, id)).filter(x => x != null);
      if (v.length < 2 || v[v.length - 2] <= 0 || v[v.length - 1] <= 0) return null;
      return Math.min(0.5, Math.max(-0.3, v[v.length - 1] / v[v.length - 2] - 1));
    };
    const windowOf = (id, from) => {   // from번째 분기부터 4개 합 [합, 연장한 분기 수]
      const g = growth(id);
      const v = [];
      let ext = 0;
      for (let i = from; i < from + 4; i++) {
        if (i < next.length) {
          v[i] = val(next[i], id);
        } else {
          const base = i - 4 < next.length ? val(next[i - 4], id) : null;   // null × 숫자는 0이 되므로 먼저 거른다
          v[i] = g != null && base != null ? base * (1 + g) : null;
          ext++;
        }
        if (v[i] == null) return [null, 0];
      }
      return ext > 3 ? [null, 0] : [v.slice(from).reduce((a, b) => a + b, 0), ext];
    };
    const best = (ids, from) => { for (const id of ids) { const r = windowOf(id, from); if (r[0] != null) return r; } return [null, 0]; };
    const guided = id => next.slice(0, 4).some(r => /^guidance/.test((r.metricsValues[id] || {}).source || ""));
    const epsId = fe.primaryEpsBasis === "adjusted" ? "eps_adjusted" : "eps_gaap";
    const EPS = [epsId], EBITDA = ["ebitda_adjusted", "ebitda"], EBIT = ["ebit_adjusted", "ebit"];
    const later = from => { const [eps, e1] = best(EPS, from), [ebitda, e2] = best(EBITDA, from); return { eps, ebitda, ext: Math.max(e1, e2) }; };
    const last4 = qs.filter(r => !unreported(r)).slice(-4).map(r => r.metricsValues.revenue.actual);
    return { qs, ntm: { eps: best(EPS, 0)[0], ebitda: best(EBITDA, 0)[0], ebit: best(EBIT, 0)[0], revenue: best(["revenue"], 0)[0], rev_ttm: last4.length === 4 ? last4.reduce((a, b) => a + b, 0) : null },
             horizons: { 2: later(4), 3: later(8) }, guided: { eps: guided(epsId), ebitda: guided("ebitda_adjusted") || guided("ebitda") } };
  };
  const { qs, ntm, horizons, guided } = await ntmOf(k);

  // 과거 레인지 — 월말 Fwd 1Y P/E·EV/EBITDA
  const z = await codemode.company_analyst_estimates({ companyKey: k, history: true });
  const hist = id => {
    const m = {};
    (z.history || []).filter(h => h.metricId === id && h.periodType === "Quarterly" && h.mean != null).forEach(h => { (m[h.reportDate] = m[h.reportDate] || []).push([h.asOf || "", h.mean]); });
    Object.values(m).forEach(a => a.sort((x, y) => (x[0] < y[0] ? -1 : 1)));
    return m;
  };
  const he = hist("analyst_eps");
  const hb = hist("analyst_ebitda");
  const ntmAt = (h, d) => {
    const ends = Object.keys(h).filter(e => e > d).sort().slice(0, 4);
    if (ends.length < 4) return null;
    let s = 0;
    for (const e of ends) {
      const known = h[e].filter(r => r[0] <= d).slice(-1)[0];
      if (!known) return null;
      s += known[1];
    }
    return s;
  };
  const px = await codemode.company_stock_prices({ companyKey: k });
  const rows = (px.prices || []).filter(p => p.closePrice != null).sort((a, b) => (a.date < b.date ? -1 : 1));
  const mc = await codemode.company_daily_ratios({ ratioId: "calculated_market_cap", companyKey: k }).catch(() => []);
  const mcAt = {};
  mc.forEach(r => { mcAt[r.date] = r.ratio; });
  const nd = qs.map(r => [r.reportDate, (r.metricsValues.net_debt || {}).actual]).filter(r => r[1] != null);
  const ndAt = d => { const c = new Date(new Date(d) - 45 * 864e5).toISOString().slice(0, 10); const x = nd.filter(r => r[0] <= c).slice(-1)[0]; return x ? x[1] : null; };
  const monthEnds = [];
  rows.forEach((r, i) => { if (i === rows.length - 1 || rows[i + 1].date.slice(0, 7) !== r.date.slice(0, 7)) monthEnds.push(r); });
  const history = [];
  monthEnds.slice(-37, -1).forEach(r => {
    const eps = ntmAt(he, r.date);
    const eb = ntmAt(hb, r.date);
    const m = mcAt[r.date];
    const net = ndAt(r.date);
    const row = { date: r.date, pe_fwd: eps > 0 ? Math.round(r.closePrice / eps * 100) / 100 : null,
                  ev_ebitda_fwd: eb > 0 && m != null && net != null ? Math.round((m + net) / eb * 100) / 100 : null };
    if (row.pe_fwd != null || row.ev_ebitda_fwd != null) history.push(row);
  });

  const peerRows = {};
  for (const p of peers) { const f = await ntmOf(p); peerRows[p] = { ...(await latest(p)), ntm: f.ntm, horizons: f.horizons }; }
  console.log(JSON.stringify({ key: k, as_of: (rows[rows.length - 1] || {}).date, target, ntm, horizons, guided,
    peers: peerRows, history, source: "Fiscal.ai Forward 배수(다음 4개 분기 추정) → Street Forward. 과거 = 월말 가격 ÷ 그 시점 다음 4개 분기 추정(company_analyst_estimates history). Data provided by Zacks Investment Research, Inc., www.zacksdata.com" }));
}
