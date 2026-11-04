async () => {
  // SPAC 과거 표본 종결 뒤 수익(scripts/tenbagger/spac_history.py, 마스터 지시 2026-11-04 4단계). LIST = `py scripts/tenbagger/spac_history.py keys` 일부(한 번에 30건 안팎).
  // 티커마다 NASDAQ_·NYSE_·AMEX_ 순으로 Fiscal 키를 찾고, 종결일 종가(없으면 다음 거래일)를 기준으로 126·252·504거래일 수익, 504일 안 최고 배수, 현재 배수.
  // 시세가 없으면 px_status "시세 없음"(상장폐지·티커 변경 — 생존 편향 표시용).
  const LIST = [];   // [[cik, "TICK1,TICK2", "YYYY-MM-DD"], …]
  const tryKey = async t => { for (const ex of ["NASDAQ", "NYSE", "AMEX"]) { try { const p = await codemode.company_stock_prices({ companyKey: ex + "_" + t });
      if ((p.prices || []).length) return [ex + "_" + t, p.prices]; } catch (e) {} } return [null, null]; };
  const out = {};
  const one = async ([cik, ticks, d]) => {
    const cands = (ticks || "").split(",").filter(Boolean).filter(t => !/[UW]$|-(UN|WT|R)$|R$/.test(t) || ticks.split(",").length === 1);
    for (const t of cands.length ? cands : (ticks || "").split(",").filter(Boolean)) {
      const [key, px] = await tryKey(t.replace(/\./g, "-"));
      if (!px) continue;
      const s = px.filter(x => x.closePrice != null).map(x => [x.date, x.closePrice]).sort((a, b) => a[0] < b[0] ? -1 : 1);
      const i0 = s.findIndex(x => x[0] >= d); if (i0 < 0) continue;
      const b = s[i0][1], at = h => s[i0 + h] ? +(s[i0 + h][1] / b - 1).toFixed(3) : null;
      const win = s.slice(i0, i0 + 505).map(x => x[1] / b);
      out[cik] = { key, r6m: at(126), r12m: at(252), r24m: at(504), max24m: +Math.max(...win).toFixed(2), now_x: +(s[s.length - 1][1] / b).toFixed(3), px_status: "ok" };
      return;
    }
    out[cik] = { px_status: "시세 없음" };
  };
  for (let i = 0; i < LIST.length; i += 6) await Promise.all(LIST.slice(i, i + 6).map(one));
  console.log(JSON.stringify(out));
}
