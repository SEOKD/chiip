async () => {
  // Fiscal.ai IR 이벤트의 문서 목록(radar/fiscal_ir_docs.py --plan이 __KEYS__·__ROLES__를 채운다, 마스터 지시 2026-11-08 AT&S 점검).
  // 문서 본문은 받지 않는다 — 역할·날짜·filingId만. 출력 → 파일 → `py radar/fiscal_ir_docs.py --put <파일>`.
  const KEYS = __KEYS__, ROLES = __ROLES__;
  const out = [];
  const one = async k => {
    try {
      const ev = await codemode.company_ir_events({ companyKey: k });
      const docs = (ev || []).filter(r => r.resourceType === "document" && ROLES.includes(r.role)).slice(0, 8)
        .map(r => ({ role: r.role, id: r.resourceId, date: r.eventDate || null, fy: r.fiscalYear || null, fq: r.fiscalQuarter || null }));
      const tr = (ev || []).find(r => r.resourceType === "transcript");
      out.push({ key: k, docs, transcript: tr ? { event: tr.resourceId, date: tr.eventDate || null } : null });
    } catch (e) {
      out.push({ key: k, error: String(e && e.message || e).slice(0, 120) });
    }
  };
  for (let i = 0; i < KEYS.length; i += 6) await Promise.all(KEYS.slice(i, i + 6).map(one));   // 동시 6개 이하
  console.log(JSON.stringify(out));
}
