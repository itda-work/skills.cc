# 한국은행 ECOS OpenAPI 개발명세서 — 발췌 인덱스

원본: 한국은행 발간 "API개발명세서" 6종 (xls, 2025-03-26 마지막 갱신)
원본 xls: 6개 파일 (각 API 서비스별)
발췌일: 2026-04-28

ECOS(Economic Statistics System, 한국은행 경제통계시스템) OpenAPI는 6개 서비스로 구성. 각 서비스의 정본 명세를 별도 md로 정리.

## 6개 API 서비스 인덱스

| 번호 | 서비스명(영문) | 한글명 | xls 파일 | md 파일 |
|------|--------------|--------|---------|---------|
| 1 | StatisticTableList | 서비스 통계 목록 | API개발명세서_서비스통계목록.xls | [01-StatisticTableList.md](01-StatisticTableList.md) |
| 2 | StatisticWord | 통계용어사전 | API개발명세서_통계용어사전.xls | [02-StatisticWord.md](02-StatisticWord.md) |
| 3 | StatisticItemList | 통계 세부항목 목록 | API개발명세서_통계세부항목목록.xls | [03-StatisticItemList.md](03-StatisticItemList.md) |
| 4 | StatisticSearch | 통계 조회 (실제 데이터) | API개발명세서_통계조회조건.xls | [04-StatisticSearch.md](04-StatisticSearch.md) |
| 5 | KeyStatisticList | 100대 통계지표 | API개발명세서_100대.xls | [05-KeyStatisticList.md](05-KeyStatisticList.md) |
| 6 | StatisticMeta | 통계메타DB | API개발명세서_통계메타DB.xls | [06-StatisticMeta.md](06-StatisticMeta.md) |

## 공통 호출 URL 패턴 (PATH 방식)

ECOS는 쿼리 파라미터가 아닌 **경로(path) 기반**으로 파라미터를 전달한다.

```
https://ecos.bok.or.kr/api/{서비스명}/{인증키}/{요청유형}/{언어구분}/{시작건수}/{종료건수}/{선택파라미터들...}
```

예시:
- `https://ecos.bok.or.kr/api/StatisticTableList/<KEY>/xml/kr/1/10/102Y004`
- `https://ecos.bok.or.kr/api/StatisticSearch/<KEY>/xml/kr/1/10/200Y001/A/2015/2021/10101`
- `https://ecos.bok.or.kr/api/KeyStatisticList/<KEY>/xml/kr/1/10`

## 공통 필수 인자

| 항목 | 위치 | 샘플 | 설명 |
|------|------|------|------|
| 서비스명 | path[1] | StatisticTableList | API 서비스명 (대소문자 구분) |
| 인증키 | path[2] | sample | 한국은행에서 발급받은 키 |
| 요청유형 | path[3] | xml | xml 또는 json |
| 언어구분 | path[4] | kr | kr(국문) / en(영문) |
| 요청시작건수 | path[5] | 1 | 결과의 시작 번호 |
| 요청종료건수 | path[6] | 10 | 결과의 끝 번호 |

## 정본 에러 코드 (6개 API 공통)

ECOS 응답은 XML/JSON으로 `RESULT` 노드 안에 `CODE`(예: `INFO-100`, `ERROR-100`)와 `MESSAGE`를 담아 반환.

### 정보 (INFO) 타입

| 코드 | 메시지 | 의미 |
|------|--------|------|
| 100 | 인증키가 유효하지 않습니다. 인증키를 확인하십시오! 인증키가 없는 경우 인증키를 신청하십시오! | 인증키 무효 (오타 또는 미발급) |
| 200 | 해당하는 데이터가 없습니다. | 정상 호출이지만 결과 0건 |

### 에러 (ERROR) 타입

| 코드 | 메시지 | 의미 |
|------|--------|------|
| 100 | 필수 값이 누락되어 있습니다. 필수 값을 확인하십시오! | 필수 인자 누락 |
| 101 | 주기와 다른 형식의 날짜 형식입니다. | 주기/날짜 포맷 불일치 |
| 200 | 파일타입 값이 누락 혹은 유효하지 않습니다. | 요청유형(xml/json) 오류 |
| 300 | 조회건수 값이 누락되어 있습니다. | 시작/종료 건수 누락 |
| 301 | 조회건수 값의 타입이 유효하지 않습니다. 정수를 입력하세요. | 건수가 정수가 아님 |
| 400 | 검색범위가 적정범위를 초과하여 60초 TIMEOUT이 발생하였습니다. | 검색 범위 초과 — 조건 좁혀 재요청 |
| 500 | 서버 오류입니다. 해당 서비스를 찾을 수 없습니다. | 서비스명 오류 또는 서버 이슈 |
| 600 | DB Connection 오류입니다. | DB 접속 오류 |
| 601 | SQL 오류입니다. | 서버 측 SQL 오류 |
| 602 | 과도한 OpenAPI호출로 이용이 제한되었습니다. 잠시후 이용해주시기 바랍니다. | 호출 제한 — 백오프 후 재시도 |

> **중요**: INFO-100과 ERROR-100은 같은 코드 100이지만 타입이 다르다. INFO-100은 인증키 무효(권한 문제), ERROR-100은 필수값 누락(요청 형식 문제). 응답 type 또는 코드 prefix(`INFO-` / `ERROR-`)로 구분 필요.

## 주기(CYCLE) 코드 (StatisticSearch 등)

| 코드 | 의미 | 날짜 형식 |
|------|------|----------|
| A | 년 | 2024 |
| S | 반년 | 2024S1, 2024S2 |
| Q | 분기 | 2024Q1 ~ 2024Q4 |
| M | 월 | 202401 |
| SM | 반월 | 202401S1 |
| D | 일 | 20240101 |

## 코드(`ecos_api.py`) 사용 endpoint 매핑

코드의 6개 함수와 매뉴얼 정합:

| 코드 함수 | 서비스명 | 매뉴얼 위치 |
|----------|---------|-----------|
| `get_table_list` | StatisticTableList | 01 md |
| `search_word` | StatisticWord | 02 md |
| `get_item_list` | StatisticItemList | 03 md |
| `search_statistics` | StatisticSearch | 04 md |
| `get_key_statistics` | KeyStatisticList | 05 md |
| (미구현) | StatisticMeta | 06 md (향후 확장) |

## 주의사항 (정본 추출 시 발견)

1. xls 파일은 코드 페이지 949(EUC-KR), Windows에서 작성. 일부 셀이 숫자로 변환되어 표시될 수 있음 (예: `101.0` → `101`로 해석).
2. 매뉴얼은 단순 코드(100, 200)로 표기하나 실제 API 응답은 prefix(`INFO-100`, `ERROR-100`)로 구분.
3. URL 끝에 trailing slash (`/`)가 필요할 수 있음 — 코드 `_build_url()` 참조.
