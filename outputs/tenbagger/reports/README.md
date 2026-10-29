# 텐배거 일일 리포트 보관함

- 매일 23:00 Chiip ten-bagger가 종목 1개를 골라 `<YYYYMMDD>_<티커>.html`(그래프 포함)과 `.json`(내용)을 만든다.
- 게시: `scripts/publish_report.py`가 GitHub `claude/reports` 브랜치에 올리고 마스터 텔레그램으로 링크를 보낸다.
- GitHub는 HTML을 소스로 보여 준다 — 그래프 화면은 텔레그램으로 받은 HTML 파일을 열거나, 저장소를 받아 브라우저로 연다.
- `log.csv`: 날짜·종목·파일·치입 판단 한 줄. 같은 종목은 30일 안에 다시 쓰지 않는다.
- 연구 후보이지 매수 권유가 아니다.
