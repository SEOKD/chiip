# Chiip Weekly Fill — 빠진 주간 상승률 지역 보충 (예약 작업 chiip-weekly-fill, 일요일 06:05 KST)

마스터 지시(2026-11-21): "이번 주 Weekly에 유럽(영국 포함), 일본, 한국, 대만, 홍콩의 주간 상승률 순위가 빠졌다. 이유를 파악하고 문제를 해결하라."
원인: 토요일 아침 TradingView 계정 일일 한도가 다른 예약 작업(Pulse Weekend·Industry)에 먼저 쓰여 Weekly의 지역 스크리너가 막혔고,
대체 원천(Easyconomics 스크리너)은 일본·유럽·대만 주간 성과를 주지 않고 한국·홍콩은 시장이 없다. 렌더러는 값을 지어내지 않고 지역 묶음만 뺐다.
대책: ① 토요일 06:00~10:30 TradingView는 Weekly만 부른다(config/tv_budget.yaml holds) ② 그래도 빠지면 이 회차가 일요일 06:05(한도 해제 직후, 이 시간도 Weekly 몫)에 채운다.

1. 가장 최근 주차 `<YYYY-Www>`(outputs/brief/에서 가장 최근 `_weekly.json`)의 `py scripts/weekly/render.py <주차>` 출력에 '상승률 지역 생략'이 없으면 **아무것도 하지 말고 끝낸다**.
2. 빠진 지역만 `.claude/skills/weekly-review/SKILL.md` 1단계대로 TradingView `mcp-tv-run-screener`(`config/weekly_movers.yaml`, `sort_by: "change|1W"`)를 지역마다 한 번씩 차례로 부른다. 기준 주는 그 주차(월~금)다 — 일요일에 부르므로 1W 값은 그 주 금요일 종가 기준이다. 결과의 as_of 날짜가 그 주 금요일이 아니면 그 지역을 쓰지 않는다.
   TradingView가 막히면(한도·훅 거부) 조용히 끝낸다. 값을 지어내지 않는다.
3. 행을 SKILL.md 2단계 형식(`region, rank, pct_change, name_ko, desc_ko, theme, ticker, as_of`)으로 쓰고 `py radar/markets/weekly_movers.py --put <파일> <주차> --merge` — 새 파일의 지역만 바꾸고 미국 행은 그대로 둔다.
4. `py scripts/weekly/render.py <주차>` → 생략 안내가 줄었는지 확인. 급등 절은 고치지 않는다.
5. 발행: `scripts/weekly/publish_weekly.py` 순서대로 Artifact 같은 URL 갱신 → 노션 같은 페이지 갱신 → `send <주차>`(수정판 1통).
6. `outputs/brief/<주차>_ops.md` ⓪에 '보충: 지역 ○곳(일 06:05)'을 덧붙인다.

금지: 다른 절 다시 쓰기, D:\local-only 읽기, 공개 채널 게시, TradingView 병렬 호출, git 커밋·푸시.
