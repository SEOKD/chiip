async () => {
  // 실적 지표 정리(Dean's Ticker ①)의 (est. …) — 마스터 지시 2026-10-30: 1순위 Fiscal.ai 자체 추정(company_estimates), 2순위 Zacks(company_analyst_estimates history).
  // 발표 전 값만 쓴다: Fiscal 칸은 asOf가 발표일(earningsDate) 전날 이전일 때만(발표 뒤엔 새 가이던스로 덮어쓴다), Zacks는 history에서 발표일 전 마지막 값.
  // 기준(GAAP·조정)이 실적 줄과 다르면 est.를 붙이지 않는다 — 예외 GPM: Fiscal 매출총이익은 GAAP뿐이라 조정 GPM 줄에도 붙인다(마스터 지시 2026-10-30).
  // 이익률 est.는 같은 제공처의 분자 est. ÷ 매출 est.(OPM = 영업이익, GPM = 매출총이익). 영업이익 금액 줄은 양식에서 뺐지만 OPM 계산에 쓴다.
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
  const zack = (rd, metric) => {
    const rows = zh.filter(h => h.metricId === metric && h.periodType === "Quarterly" && String(h.reportDate).slice(0, 7) === String(rd).slice(0, 7) && pre(h.asOf));
    const r = rows.sort((a, b) => String(a.asOf) < String(b.asOf) ? -1 : 1).slice(-1)[0];
    return r ? { est: r.mean, src: "zacks", asOf: r.asOf, n: r.numEstimates } : null;
  };
  // guidance_calculated(연간 가이던스를 분기로 나눈 값)는 3순위 — Zacks가 없을 때만(2026-10-30 FTAI는 Zacks, 프리즈미안은 Zacks 없음 → Fiscal 계산값)
  const calc = (d, key) => d && d.periodType === "Quarterly" && (d.metricsValues[key] || {}).source === "guidance_calculated";
  const fis = (d, key, allowCalc) => { const c = d && d.metricsValues[key]; return c && c.mean != null && pre(c.asOf) && (allowCalc || !calc(d, key)) ? { est: c.mean, src: "fiscal:" + c.source, asOf: c.asOf, basis: c.basis, actual: c.actual } : null; };
  const lines = { revenue: ["revenue", "analyst_revenue"], ebitda_adjusted: ["ebitda_adjusted", "analyst_ebitda"], ebit_adjusted: ["ebit_adjusted", "analyst_ebit"], ebit: ["ebit", null], eps_adjusted: ["eps_adjusted", "analyst_eps"], eps_gaap: ["eps_gaap", null],
    gross_profit: ["gross_profit", null], operating_cash_flow: ["operating_cash_flow", null], capex: ["capex", null], free_cash_flow: ["free_cash_flow", null] };
  const pickFor = d => {
    if (!d) return null;
    const o = {};
    for (const [name, [fk, zk]] of Object.entries(lines)) o[name] = fis(d, fk) || (zk ? zack(d.reportDate, zk) : null) || fis(d, fk, true);
    const prov = v => String(v.src).split(":")[0];                                // fiscal / zacks — 이익률은 같은 제공처끼리만 나눈다
    const ratio = (num, rv, basis) => num && rv && prov(num) === prov(rv) ? { est: num.est / rv.est, src: num.src + "÷" + rv.src, asOf: num.asOf, basis, derived: true } : null;
    o.opm_adjusted = ratio(o.ebit_adjusted, o.revenue, "adjusted"); o.opm = ratio(o.ebit, o.revenue, "gaap");
    o.gpm = ratio(o.gross_profit, o.revenue, "gaap");                              // Fiscal 매출총이익은 GAAP 기준 — 조정 GPM 줄에도 붙이고 기준 차이는 기록 파일에
    return o;
  };
  const pick = { reported: pickFor(rep), guidance: pickFor(next) };
  const zacks_used = Object.values(pick).some(p => p && Object.values(p).some(v => v && v.src === "zacks"));
  console.log(JSON.stringify({ key: k, earningsDate: ed, reported: rep && rep.reportDate, guidance_period: next && next.reportDate, primaryEpsBasis: fe.primaryEpsBasis, pick, zacks_used,
    attribution: zacks_used ? "Data provided by Zacks Investment Research, Inc., www.zacksdata.com" : null }));
}
