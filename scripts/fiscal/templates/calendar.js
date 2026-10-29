async () => {
  // 실적 일정(과거·예정) — 감시 목록만. `py radar/markets/earnings_calendar.py --fiscal-code`가 __US__·__KEYS__·__START__·__END__를 채워 준다.
  // 미국은 티커 50개 묶음(ticker=, 식별자 50개 상한, 미국 거래소만 남김), 그 밖은 회사 키 묶음(companyKey=). 없는 키(코스닥 등)는 조용히 빠지지만 알 수 없는 거래소 접두어(XKOS_ 등)는 묶음 전체를 실패시키므로
  // 반으로 나눠 다시 묻고 끝내 없는 키는 missing으로 낸다. 출력 → 파일 → `py radar/markets/earnings_calendar.py --fiscal-put <파일>`
  const US = __US__, KEYS = __KEYS__, S = "__START__", E = "__END__";
  const ROLES = new Set(["financial_results_release", "earnings_call_for_results"]);
  const US_EX = new Set(["NYSE", "NASDAQ", "NYSEAMERICAN", "NYSEARCA", "AMEX", "BATS", "CBOE"]);
  const rows = [], missing = [], errors = [];
  const call = (p, q) => codemode.events_calendar(Object.assign({ startDate: S, endDate: E, pageSize: 1000 }, p))
    .then(r => ((r && r.data) || []).forEach(x => rows.push(Object.assign(x, { q }))));
  const byKey = async ks => {
    try { await call({ companyKey: ks.join(",") }, "key"); }
    catch (e) {
      if (ks.length === 1) { missing.push(ks[0]); return; }
      const h = Math.ceil(ks.length / 2);
      await byKey(ks.slice(0, h)); await byKey(ks.slice(h));
    }
  };
  const jobs = [];
  for (let i = 0; i < US.length; i += 50) { const t = US.slice(i, i + 50); jobs.push(() => call({ ticker: t.join(",") }, "us").catch(e => errors.push(String(e.message || e).slice(0, 120)))); }
  for (let i = 0; i < KEYS.length; i += 20) { const t = KEYS.slice(i, i + 20); jobs.push(() => byKey(t)); }
  for (let i = 0; i < jobs.length; i += 6) await Promise.all(jobs.slice(i, i + 6).map(f => f()));   // 동시 6개 이하
  const out = {};
  rows.filter(x => ROLES.has(x.eventRole)).forEach(x => {
    const pl = x.primaryListing || {};
    if (x.q === "us" && !US_EX.has(pl.exchangeCode)) return;   // 같은 티커의 해외 종목(예 TSX_SU) 제외
    const k = `${x.companyKey}|${x.eventDate}`, cur = out[k];
    if (cur) { cur.roles.push(x.eventRole); cur.utc = cur.utc || x.eventDatetimeUtc; cur.session = cur.session || x.eventSession; return; }
    out[k] = { key: x.companyKey, ticker: pl.ticker, exchange: pl.exchangeCode, country: x.headquartersCountryCode, name: x.displayNameEnglish,
      date: x.eventDate, status: x.eventStatus, session: x.eventSession, utc: x.eventDatetimeUtc, period: x.periodLabel,
      window: x.dateWindow, q: x.q, roles: [x.eventRole] };
  });
  console.log(JSON.stringify({ start: S, end: E, events: Object.values(out), missing, errors }));
}
