async () => {
  // 추정치 수정 폭 재료 — 여러 종목 한 번에(마스터 선택 2026-11-14). `py scripts/tenbagger/breadth.py --code <키…>`가 키 목록을 채운다.
  // 출력 → 파일 → `py scripts/tenbagger/breadth.py --put <파일>` → knowledge/models/estimates/breadth.json. Zacks 수치라 표기 의무.
  // 섹터 단위(2026-11-14): 출력이 커지지 않게 샌드박스 안에서 사건만 만든다 — breadth.py events()·by_day()와 같은 규칙
  // (열린 기간, 애널리스트 수가 같은 채 평균 변화 ≥ 0.1%, 같은 날·지표는 다수 방향 1건, 수만 바뀐 날은 cov).
  const KEYS = __KEYS__, TOL = 0.001;
  const today = new Date().toISOString().slice(0, 10);
  const cut = new Date(Date.now() - 95 * 864e5).toISOString().slice(0, 10);
  const M = ["analyst_eps", "analyst_revenue", "analyst_ebitda", "analyst_ebit"];
  const out = {}, errors = [];
  const one = async k => {
    try {
      const z = await codemode.company_analyst_estimates({ companyKey: k, history: true });
      const ser = {};
      for (const x of z.history || []) {
        if (!M.includes(x.metricId) || !x.reportDate || x.reportDate <= today || !x.asOf || x.mean == null) continue;
        (ser[`${x.metricId}|${x.periodType}|${x.reportDate}`] ||= []).push(x);
      }
      const day = {};
      for (const v of Object.values(ser)) {
        v.sort((a, b) => (a.asOf < b.asOf ? -1 : 1));
        for (let i = 1; i < v.length; i++) {
          const a = v[i - 1], b = v[i];
          if (b.asOf < cut) continue;
          const c = (day[`${b.asOf}|${b.metricId}`] ||= { up: 0, down: 0, cov: 0 });
          if (a.numEstimates !== b.numEstimates) { c.cov++; continue; }
          if (!a.mean) continue;
          const ch = a.mean > 0 ? b.mean / a.mean - 1 : (b.mean - a.mean) / Math.abs(a.mean);
          if (Math.abs(ch) >= TOL) c[ch > 0 ? "up" : "down"]++;
        }
      }
      const events = [];
      for (const [kk, c] of Object.entries(day)) {
        const [d, m] = kk.split("|");
        if (c.up !== c.down) events.push([d, m, c.up > c.down ? "up" : "down"]);
        else if (!c.up && c.cov) events.push([d, m, "cov"]);
      }
      // 일괄(섹터) 모드는 건수만 — [상향, 하향, 커버리지] × (EPS 30일, EPS 90일, 전체 30일, 전체 90일). 단일 종목은 events를 쓴다
      const cnt = (days, eps) => { const lo = new Date(Date.now() - days * 864e5).toISOString().slice(0, 10);
        const s = events.filter(e => e[0] > lo && (!eps || e[1] === "analyst_eps")); return ["up", "down", "cov"].map(t => s.filter(e => e[2] === t).length); };
      out[k] = __COUNTS__ ? { asOf: today, c: [...cnt(30, 1), ...cnt(90, 1), ...cnt(30, 0), ...cnt(90, 0)] } : { asOf: today, events: events.sort() };
    } catch (e) { errors.push(`${k}: ${String(e.message || e).slice(0, 60)}`); }
  };
  for (let i = 0; i < KEYS.length; i += 6) await Promise.all(KEYS.slice(i, i + 6).map(one));   // 동시 6개 이하
  console.log(JSON.stringify({ out, errors, source: "Fiscal.ai company_analyst_estimates history(Zacks). Data provided by Zacks Investment Research, Inc., www.zacksdata.com" }));
}
