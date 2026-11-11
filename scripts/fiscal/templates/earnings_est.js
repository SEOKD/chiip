async () => {
  // 실적 지표 정리(Dean's Ticker ①)의 (est. …) — 마스터 지시 2026-10-30: 1순위 Fiscal.ai 자체 추정(company_estimates), 2순위 Zacks(company_analyst_estimates history) — Fiscal 칸이 없을 때만.
  // 발표 전 값만 쓴다: Fiscal 칸은 asOf가 발표일(earningsDate) 전날 이전일 때만(발표 뒤엔 새 가이던스로 덮어쓴다), Zacks는 history에서 발표일 전 마지막 값.
  // 기준(GAAP·조정)이 실적 줄과 다르면 est.를 붙이지 않는다 — 예외 GPM: Fiscal 매출총이익은 GAAP뿐이라 조정 GPM 줄에도 붙인다(마스터 지시 2026-10-30).
  // 이익률 est.는 같은 제공처의 분자 est. ÷ 매출 est.(OPM = 영업이익, GPM = 매출총이익). 영업이익 금액 줄은 양식에서 뺐지만 OPM 계산에 쓴다.
  // 이익률은 표시한 매출 est.와 같은 제공처 쌍을 먼저(보통 Fiscal ÷ Fiscal, 매출이 Zacks일 때만 Zacks EBIT ÷ Zacks 매출), 없으면 다른 제공처 쌍 —
  // 2026-10-30 STRL·EME: 분자는 Fiscal·매출은 Zacks로 각각 골라 '제공처 불일치'로 GPM·OPM est.가 빠지던 결함 수정.
  // __KEY__ = NASDAQ_SNDK 형식. 출력 pick[분기][지표] = {est, src: 'fiscal:<source>'|'zacks', asOf} | null. zacks_used=true면 Zacks 표기를 단다.
  const k = "__KEY__";
  const [fe, z] = await Promise.all([
    codemode.company_estimates({ companyKey: k }),
    codemode.company_analyst_estimates({ companyKey: k, history: true }).catch(() => ({ history: [] }))]);
  const qs = fe.data.filter(d => d.periodType === "Quarterly");
  const rep = qs.filter(d => d.earningsDate).slice(-1)[0];                       // 방금 발표한 분기
  const next = qs.find(d => !d.earningsDate && d.reportDate > (rep || {}).reportDate);   // 가이던스 분기
  const ed = rep ? String(rep.earningsDate).slice(0, 10) : null;                  // 다음 분기 가이던스도 같은 발표일 기준
  const pre = a => a && ed && String(a).slice(0, 10) < ed;
  const zh = z.history || [];
  const zack = (rd, metric, pt = "Quarterly") => {
    const rows = zh.filter(h => h.metricId === metric && h.periodType === pt && String(h.reportDate).slice(0, 7) === String(rd).slice(0, 7) && pre(h.asOf));
    const r = rows.sort((a, b) => String(a.asOf) < String(b.asOf) ? -1 : 1).slice(-1)[0];
    return r ? { est: r.mean, src: "zacks", asOf: r.asOf, n: r.numEstimates } : null;
  };
  // Fiscal.ai 칸은 source와 무관하게 1순위(guidance·guidance_adjusted·guidance_calculated·model·agentic_consensus) — Zacks는 Fiscal 발표 전 칸이 없을 때만
  // (마스터 지시 2026-10-30 "여전히 Zacks에서 가져오는 경우가 많다 — Fiscal.ai 컨센서스를 1순위로". 그 전엔 분기 guidance_calculated를 Zacks 뒤로 미뤄 STRL 매출·EPS·EBITDA가 Zacks로 갔다)
  const fis = (d, key) => { const c = d && d.metricsValues[key]; return c && c.mean != null && pre(c.asOf) ? { est: c.mean, src: "fiscal:" + c.source, asOf: c.asOf, basis: c.basis, actual: c.actual } : null; };
  const lines = { revenue: ["revenue", "analyst_revenue"], ebitda_adjusted: ["ebitda_adjusted", "analyst_ebitda"], ebit_adjusted: ["ebit_adjusted", "analyst_ebit"], ebit: ["ebit", null], eps_adjusted: ["eps_adjusted", "analyst_eps"], eps_gaap: ["eps_gaap", null],
    gross_profit: ["gross_profit", null], operating_cash_flow: ["operating_cash_flow", null], capex: ["capex", null], free_cash_flow: ["free_cash_flow", null] };
  const pickFor = (d, pt = "Quarterly") => {
    if (!d) return null;
    const o = {};
    for (const [name, [fk, zk]] of Object.entries(lines)) o[name] = fis(d, fk) || (zk ? zack(d.reportDate, zk, pt) : null);
    const prov = v => String(v.src).split(":")[0];                                // fiscal / zacks — 이익률은 같은 제공처끼리만 나눈다
    const side = (p, fk, zk) => p === "zacks" ? (zk ? zack(d.reportDate, zk, pt) : null) : fis(d, fk);
    const ratio = (fk, zk, basis) => {
      for (const p of (o.revenue && prov(o.revenue) === "zacks" ? ["zacks", "fiscal"] : ["fiscal", "zacks"])) {
        const num = side(p, fk, zk), rv = side(p, "revenue", "analyst_revenue");
        if (num && rv) return { est: num.est / rv.est, src: num.src + "÷" + rv.src, asOf: num.asOf, num: num.est, rev: rv.est, basis, derived: true };
      }
      return null;
    };
    o.opm_adjusted = ratio("ebit_adjusted", "analyst_ebit", "adjusted"); o.opm = ratio("ebit", null, "gaap");
    o.gpm = ratio("gross_profit", null, "gaap");                                   // Fiscal 매출총이익은 GAAP 기준 — 조정 GPM 줄에도 붙이고 기준 차이는 기록 파일에
    return o;
  };
  // 연간 가이던스 est.(마스터 지시 2026-11-11 "Guidance에도 컨센서스(est.)가 붙도록 — 가끔 빠져 있더라"): 그때까지 분기만 골라 'FY Guidance' 줄은 늘 비었다(CLFD FY27 매출).
  // 발표 분기가 속한 회계연도(fy_current)와 다음 회계연도(fy_next) — 회사가 이번에 낸 연간 가이던스가 어느 해인지에 맞춰 고른다
  const ys = fe.data.filter(d => d.periodType === "Annual").sort((a, b) => String(a.reportDate) < String(b.reportDate) ? -1 : 1);
  const fyc = rep ? ys.find(d => d.reportDate >= rep.reportDate) : null;
  const fyn = fyc ? ys.find(d => d.reportDate > fyc.reportDate) : null;
  const pick = { reported: pickFor(rep), guidance: pickFor(next), fy_current: pickFor(fyc, "Annual"), fy_next: pickFor(fyn, "Annual") };
  const zacks_used = Object.values(pick).some(p => p && Object.values(p).some(v => v && v.src === "zacks"));
  // 출력 파일 → `py scripts/fiscal/estimates.py --pick <파일>`이 저장해 둔 Fiscal 추정과 Easyconomics로 reported 빈칸을 보완한다(2026-11-01)
  const act = rep ? Object.fromEntries(["revenue", "eps_adjusted", "ebit_adjusted", "ebitda_adjusted"].flatMap(m => { const c = rep.metricsValues[m]; return c ? [[m, c.actual], [m + "_basis", c.basis]] : []; })) : {};
  console.log(JSON.stringify({ key: k, earningsDate: ed, reported: rep && rep.reportDate, period: rep ? `${rep.calendarYear}Q${rep.calendarQuarter}` : null, reported_actual: act, guidance_period: next && next.reportDate, fy_current_period: fyc && fyc.reportDate, fy_next_period: fyn && fyn.reportDate, primaryEpsBasis: fe.primaryEpsBasis, pick, zacks_used,
    attribution: zacks_used ? "Data provided by Zacks Investment Research, Inc., www.zacksdata.com" : null }));
}
