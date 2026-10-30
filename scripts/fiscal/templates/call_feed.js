async () => {
  // 어닝콜 인사이트 피드 데이터(마스터 지시 2026-10-30 "Fiscal.ai에 어닝콜 스크립트가 실적 발표 이후 뒤늦게 올라오면 뉴팩트 정리와 함께 인사이트 피드도").
  // `py scripts/insight/call_feed.py code <회사 키> <q분기-연도>`가 키·이벤트·직전 이벤트·임계값을 채운다. 출력 → 파일 → `py scripts/insight/call_feed.py calc <파일> <키> <이벤트>`.
  // ① 종가: 종목·시장 근사(미국 대형주 6종 동일가중 — Fiscal에 지수·ETF가 없다)·직접 경쟁사 3곳, 최근 140거래일 — 발표 반응 AR·β·게재까지의 표류
  // ② 이번·직전 콜 Q&A 통계: 질문 수·질문 회사 수·경영진 답변 길이·짧은 답/회피 표현 후보(Hollander, Pronk & Roelofsen 2010 — 답하지 않음도 신호)
  // 트랜스크립트는 라이선스 자료 — 질문 앞부분은 판단용으로만, 텔레그램에는 요지만 자기 말로(인용 15단어 이하).
  const K = "__KEY__", EV = "__EVENT__", PREV = "__PREV__";
  const MKT = ["NASDAQ_AAPL", "NASDAQ_MSFT", "NASDAQ_NVDA", "NASDAQ_AMZN", "NASDAQ_GOOGL", "NASDAQ_META"];
  const N = 140, SHORT = __SHORT__, QMIN = __QMIN__, errors = [];   // SHORT·QMIN = config/insight/call_feed.yaml
  const closes = async k => {
    try {
      const p = await codemode.company_stock_prices({ companyKey: k });
      let r = (p.prices || []).filter(x => x.closePrice != null).slice(0, N).reverse();
      // 미확정 마지막 봉 제외(prices.js와 같은 규칙 — 장중 행은 거래량이 직전 20일 중앙값의 1% 미만으로 온다)
      const v = r.slice(-21, -1).map(x => x.volume || 0).sort((a, b) => a - b), med = v.length ? v[Math.floor(v.length / 2)] : 0;
      if (r.length > 21 && (r[r.length - 1].volume || 0) < 0.01 * med) r = r.slice(0, -1);
      return { cur: p.tradingCurrency || null, rows: r.map(x => [x.date, x.closePrice]) };
    } catch (e) { errors.push(k + ": " + String(e && e.message || e).slice(0, 80)); return null; }
  };
  const tr = async ev => { try { return await codemode.company_ir_events_transcript({ companyKey: K, eventKey: ev }); } catch (e) { errors.push(ev + ": " + String(e && e.message || e).slice(0, 80)); return null; } };
  const REFUSE = /(not going to (comment|get into|provide|break)|won'?t (comment|get into|provide)|don'?t (want to|provide|guide|break out|comment)|too early to|not (in a position|ready) to|prefer not to|we'?ll (share|update) (more|that) (later|at)|not something we disclose)/i;
  const qa = t => {
    if (!t) return null;
    const who = Object.fromEntries((t.speakers || []).map(s => [s.speaker, s]));
    const sec = (t.sections || []).find(s => s.sectionType === "qa");
    const paras = (t.transcript && t.transcript.paragraphs) || [];
    const inQa = p => sec && p.start != null && p.start >= (sec.start || 0) && (sec.end == null || p.start <= sec.end);
    const words = s => (String(s || "").match(/\S+/g) || []).length;
    let prepared = 0, cur = null;
    const qs = [];
    for (const p of paras) {
      const typ = (who[p.speaker] || {}).speakerType;
      if (!inQa(p)) { if (typ === "company_management") prepared += words(p.text); continue; }
      if (typ === "analyst") {   // 인사·확인 말("Thanks", "can you hear me?")은 질문이 아니다 — 물음표가 있거나 QMIN단어 이상만
        const isQ = (/\?/.test(p.text) && !/hear me\??\s*$/i.test(p.text.trim())) || words(p.text) >= QMIN;
        cur = isQ ? { firm: (who[p.speaker] || {}).company || null, q: p.text.slice(0, 160), words: 0, refuse: false } : null;
        if (cur) qs.push(cur);
      }
      else if (typ === "company_management" && cur) { cur.words += words(p.text); if (REFUSE.test(p.text)) cur.refuse = true; }
    }
    const ans = qs.filter(q => q.words > 0);
    return { event: t.event && t.event.eventKey, qa_found: !!sec, prepared_words: prepared, questions: qs.length,
      firms: new Set(qs.map(q => q.firm).filter(Boolean)).size,
      answer_words_avg: ans.length ? Math.round(ans.reduce((a, q) => a + q.words, 0) / ans.length) : null,
      short_or_refuse: qs.filter(q => q.refuse || (q.words > 0 && q.words < SHORT)).slice(0, 8) };
  };
  const [me, peers, tNow, tPrev] = await Promise.all([closes(K), codemode.company_peers({ companyKey: K }).catch(() => ({ peers: [] })), tr(EV), PREV ? tr(PREV) : null]);
  const pk = (peers.peers || []).filter(p => p.peerRelationship === "direct_competitor" && p.companyKey && p.companyKey !== K).slice(0, 3).map(p => p.companyKey);
  const keys = MKT.filter(k => k !== K).concat(pk), series = {};
  for (let i = 0; i < keys.length; i += 6) (await Promise.all(keys.slice(i, i + 6).map(closes))).forEach((r, j) => { if (r) series[keys[i + j]] = r.rows; });
  // 동일가중 일간 수익률(날짜별로 있는 종목만 평균) — 출력 크기를 줄이려고 여기서 묶는다
  const basket = ks => { const acc = {}; ks.filter(k => series[k]).forEach(k => { const r = series[k]; for (let i = 1; i < r.length; i++) if (r[i - 1][1]) (acc[r[i][0]] = acc[r[i][0]] || []).push(r[i][1] / r[i - 1][1] - 1); });
    return Object.fromEntries(Object.keys(acc).sort().map(d => [d, Math.round(acc[d].reduce((a, b) => a + b, 0) / acc[d].length * 1e5) / 1e5])); };
  console.log(JSON.stringify({ key: K, event: EV, prev: PREV, currency: me && me.cur, stock: me && me.rows, market: MKT.filter(k => series[k]), peers: pk.filter(k => series[k]),
    mkt_ret: basket(MKT), peer_ret: basket(pk), call: qa(tNow), prev_call: qa(tPrev), errors }));
}
