# 노션 운영 규칙

> CLAUDE.md '출력 채널'에서 옮긴 마스터 지시(2026-10-31, AAP-20261031-02). 새 지시도 여기에 적는다.

- **마스터 노션 구조(이름·역할 고정, `config/notion.yaml` pages):** **Insights** = 마스터 인사이트 글(치입 검토 대상, 글 아래 '치입 검토' 하위 페이지만 작성) / **Informations** = 마스터 수집 정보(근거 재료, IB 요지는 라이선스 취급·채널체크는 필드 인텔 가능성 → invest·public 금지) / **Stocks** = 마스터 종목·테마 커버리지(어닝 캘린더·알파 점수 대상에 항상 포함). 쓰기 허용은 텐배거 리포트와 최상위 Weekly 페이지 아래 주차별 Weekly Review(2026-10-31 마스터 지시, `config/notion.yaml` pages.weekly)뿐(2026-10-30 마스터 지시): '<한국어명> <티커>' 종목 페이지가 없으면 생성, 그 아래 '텐배거 리포트 YYYY-MM-DD — …' 하위 페이지(`scripts/tenbagger/report_notion.py`, 기록 `outputs/tenbagger/reports/notion_log.csv`) — 마스터가 쓴 본문은 고치지 않는다. 리포트 하위 페이지 맨 위에 HTML 임베드(차트 포함 전체 리포트).
- **노션 올림 즉시 처리(마스터 지시 2026-10-28 '일일이 입력하면 챗봇'):** 마스터가 Insights·Informations·Stocks에 페이지를 올리거나 고치면 치입이 알아서 역할별 분석(스킬 `notion-intake`) → `outputs/report/notion/` + 텔레그램. 감지는 `radar/notion_watch.py`(NOTION_TOKEN, 5분·수정 감지) 또는 예약 작업 `chiip-notion-watch`(토큰 전, 매시간 새 페이지). 상태 `scripts/notion_state.py`.
- **Notion(비공개 허브 '치입 인텔리전스') = ⭐ 인텔 아카이브(+ 구 오피니언·인사이트 DB).** ⭐로 고른 정보만 기록(요지·링크, 원문 복제 금지, local-only·필드 인텔 금지). 공개 사이트에 올리는 글은 public 모드 규칙 + 마스터가 직접 게시.
