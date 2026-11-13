async () => {
  // 추정치 수정 폭 재료 — 여러 종목 한 번에(마스터 선택 2026-11-14). `py scripts/tenbagger/breadth.py --code <키…>`가 __KEYS__를 채운다.
  // 출력 → 파일 → `py scripts/tenbagger/breadth.py --put <파일>` → knowledge/models/estimates/breadth.json. Zacks 수치라 표기 의무.
  const KEYS = __KEYS__;
  const today = new Date().toISOString().slice(0, 10);
  const cut = new Date(Date.now() - 100 * 864e5).toISOString().slice(0, 10);
  const M = ["analyst_eps", "analyst_revenue", "analyst_ebitda", "analyst_ebit"];
  const out = {}, errors = [];
  const one = async k => {
    try {
      const z = await codemode.company_analyst_estimates({ companyKey: k, history: true });
      const h = (z.history || []).filter(x => M.includes(x.metricId) && x.reportDate && x.reportDate > today);
      const base = {}, rows = [];
      for (const x of h) {   // 창 앞의 마지막 값 하나는 기준으로 남긴다
        const s = `${x.metricId}|${x.periodType}|${x.reportDate}`;
        if (!x.asOf || x.asOf < cut) base[s] = x; else rows.push(x);
      }
      const pack = x => [x.metricId, x.periodType === "Annual" ? "A" : "Q", x.reportDate, x.asOf, x.mean, x.numEstimates];
      out[k] = { asOf: today, rows: [...Object.values(base), ...rows].map(pack) };
    } catch (e) { errors.push(`${k}: ${String(e.message || e).slice(0, 80)}`); }
  };
  for (let i = 0; i < KEYS.length; i += 6) await Promise.all(KEYS.slice(i, i + 6).map(one));   // 동시 6개 이하
  console.log(JSON.stringify({ out, errors, source: "Fiscal.ai company_analyst_estimates history(Zacks). Data provided by Zacks Investment Research, Inc., www.zacksdata.com" }));
}
