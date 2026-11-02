# ECOS 한국은행 경제통계 — 요청 URL 과 collect_econ.py 상세

제안서의 경제 환경 분석에 필요한 거시경제 지표를 수집합니다.
스크립트(`collect_econ.py`)가 ECOS 에 직접 요청하고 1000행씩 `list_total_count` 까지 받아 전량 대조·정리한다.
명령 한 번에 결과가 나온다. 옵션 전체의 정본은 `SKILL.md` 다.

## 인증키

1. https://ecos.bok.or.kr/api/ 회원가입 → 인증키 신청(가입 시 즉시 발급)
2. `.env` 에 `ECOS_API_KEY=<키>` 로 적는다 — 스크립트가 URL **경로**의 키 자리에 넣는다(출력·오류의 URL 에는 `***` 로 가린다)

> 한국은행 공개 시험 키 `sample` 은 최대 10건만 준다. 이 스킬의 실측 픽스처(`tests/fixtures/*_sample.json`)가 그것으로 받은 응답이다.

## 요청 URL (경로 방식)

```
https://ecos.bok.or.kr/api/<서비스>/<키>/json/kr/<시작행>/<끝행>/<선택 세그먼트…>/
```

| 명령 | 서비스 | 선택 세그먼트 | 예 |
|------|--------|--------------|----|
| `key` | KeyStatisticList | — | `…/KeyStatisticList/<키>/json/kr/1/1000/` |
| `search` | StatisticSearch | 통계표코드/주기/시작/끝[/항목1[/항목2…]] | `…/StatisticSearch/<키>/json/kr/1/1000/901Y009/A/2020/2024/` |
| `items` | StatisticItemList | 통계표코드 | `…/StatisticItemList/<키>/json/kr/1/1000/901Y009/` |
| `tables` | StatisticTableList | — | `…/StatisticTableList/<키>/json/kr/1/1000/` |
| `word` | StatisticWord | 용어(한글 그대로) | `…/StatisticWord/<키>/json/kr/1/1000/기준금리/` |

- 한 요청은 1000행(`1/1000`, `1001/2000`, …)씩 받는다. 응답의 `list_total_count` 가 전체 행 수다.
- 응답 본문에는 행 범위가 없다 — 스크립트가 요청한 시작행과 받은 행 수로 범위가 1행부터 빈틈없이 이어지는지,
  겹치지 않는지, 모든 쪽의 `list_total_count` 가 같은지(다르면 받는 사이 자료가 바뀌었다) 보고, 어긋나면 전 쪽을 한 번 더 받는다.
  그래도 비면 빈 범위를 `missing_ranges` 로 알려 준다.
- 세그먼트는 스크립트가 하나씩 퍼센트 인코딩한다(한글 용어 `기준금리` → `%EA%B8%B0…`, 한 번만). `--word` 에는 한글을 그대로 준다.
- 응답 크기(2026-09-30 `sample` 실측 기준 list_total_count): 100대 지표 101 · 통계표 목록 844 · 901Y009 세부항목 1,743 · 901Y009 월간 2020~2024 60.

## 서브커맨드

| 커맨드 | 입력(서비스) | 핵심 데이터 |
|-------|-------------|-----------|
| `key` | KeyStatisticList | GDP, 금리, 환율, 물가, 통화량 등 100대 지표 |
| `search` | StatisticSearch | 시점별 수치 데이터(값이 숫자가 아닌 행은 빼고 수를 `skipped_non_numeric` 에 남김) |
| `items` | StatisticItemList | 항목코드 조회 (search 전 확인용) |
| `tables` | StatisticTableList | 통계표코드 확인 |
| `word` | StatisticWord | 경제 용어 공식 정의 |

```bash
python3 scripts/collect_econ.py search --stat 901Y009 --period year --start 2020 --end 2024
python3 scripts/collect_econ.py search --stat 731Y003 --period day --start 20240102 --end 20240131 --item1 0000003
python3 scripts/collect_econ.py --format table items --stat 901Y009
```

Windows: `python3` → `py -3`

## 주기별 날짜 형식

| 주기 | 코드 | 날짜 형식 | 예시 |
|------|------|---------|------|
| 연간 | year (A) | `YYYY` | `2024` |
| 반기 | semi (S) | `YYYYS1` | `2024S1` |
| 분기 | quarter (Q) | `YYYYQ1` | `2024Q1` |
| 월간 | month (M) | `YYYYMM` | `202401` |
| 일간 | day (D) | `YYYYMMDD` | `20240101` |

## 자주 쓰는 통계표코드

| 지표 | 코드 | 주기 | 주요 항목코드 |
|------|------|------|-----------|
| 소비자물가지수 (CPI) | `901Y009` | M, A | (총지수 등 품목별) |
| GDP (원계열, 실질) | `200Y106` | Q, A | |
| GDP (원계열, 명목) | `200Y105` | Q, A | |
| 환율 (원/달러 종가) | `731Y003` | D | `0000003` (원/달러 종가) |
| 한국은행 기준금리·여수신금리 | `722Y001` | D | |
| 국민소득 (명목, 연간) | `200Y113` | A | |

> 코드를 모르면 `items`(StatisticItemList)로 확인하세요.

## 에러 코드

| 코드 | 의미 | 조치 |
|------|------|------|
| INFO-100 | 인증키 유효하지 않음 | `.env` 의 `ECOS_API_KEY` 확인 |
| INFO-200 | 데이터 없음 | 날짜/항목코드 변경 |
| ERROR-100 | 필수값 누락 | stat_code, period, 날짜 확인 |
| ERROR-101 | 주기와 날짜 형식 불일치 | 위 날짜 형식 표 참조 |
| ERROR-400 | 검색범위 초과 (60초 TIMEOUT) | 조회 범위 축소 |
| ERROR-602 | 과도한 호출 → 이용 제한 | 잠시 후 재시도 |
