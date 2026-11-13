async () => {
  // 알파 섹터 보정 관문 시세(scripts/alpha/sector_shadow.py --price-code, ADR-028) — 출력 → 파일 → py scripts/alpha/sector_shadow.py --put-prices <파일>
  // 키 없음(빼 둠): __MISSING__
  const keys = __KEYS__, start = "__START__", out = {}, errors = [];
  const ks = Object.keys(keys);
  for (let i = 0; i < ks.length; i += 4) {
    await Promise.all(ks.slice(i, i + 4).map(async t => {
      try {
        const p = await codemode.company_stock_prices({ companyKey: keys[t] });
        out[t] = (p.prices || []).filter(x => x.closePrice != null && x.date >= start)
          .sort((a, b) => a.date < b.date ? -1 : 1).map(x => [x.date, x.closePrice]);
      } catch (e) { errors.push(t + ": " + String(e && e.message || e).slice(0, 60)); }
    }));
  }
  console.log(JSON.stringify({ prices: out, errors }));
}
