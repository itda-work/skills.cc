# Changelog — itda-cc:calendar

## 0.1.0 (2026-11-02)

- 첫 판. Claude Code 전용 — 스크립트 `scripts/cal.py` 가 `.env` 하나(`--env-file` > `./.env` > `~/.env`)의 메일 계정 앱 비밀번호로
  CalDAV 에 직접 붙는다(표준 라이브러리만 — caldav·icalendar 의존 없음). 기능 범위는 itda-work:calendar 0.7.4(itda-hyve 판)와 같다:
  계정 · 캘린더 목록 · 기간 조회·검색 · 한 건 상세 · 만들기·고치기 · 지우기(빈 시간은 조회 결과로 계산).
- 네이버·아이클라우드·직접 입력(`CALDAV_URL`, https 만). Google·다음 캘린더는 `supported: false` 로 사유를 밝힌다.
- 수정은 조회한 etag 로만(`If-Match`, 다르면 쓰지 않고 `etag_conflict`) · 준 필드만 줄 단위로 바꾸고 나머지 원문 보존 · `SEQUENCE` 증가.
- 삭제 게이트를 스크립트가 강제한다 — `--confirm` 없으면 미리보기만(exit 3). 토큰은 계정·일정·etag 에 묶이고 10분 만료·1회용.
- 참석자 있는 일정·약한 etag·etag 없는 일정·깨진 원문은 수정·삭제를 거부한다(`reason`).
- 서울 시각 일정은 `TZID=Asia/Seoul`(+VTIMEZONE)로 저장한다. 새 일정의 UID·PRODID 에 제품·조직 이름을 싣지 않는다.
- 네이버는 time-range REPORT 대신 객체 목록 + multiget 으로 읽고, UID 조회를 거부하는 서버(iCloud)는 객체 열거로 찾는다.
- 라이브(2026-11-02, 네이버·iCloud): 네이버는 GET·PUT 응답에 ETag 헤더를 싣지 않아 수정·삭제가 전부 `no_etag` 로 막혔다 —
  헤더가 없으면 PROPFIND `getetag`(Depth 0)로 받는다(가짜 서버 회귀 테스트, 고치기 전 코드로 RED 확인). iCloud PUT 은 403 없이 성립.
