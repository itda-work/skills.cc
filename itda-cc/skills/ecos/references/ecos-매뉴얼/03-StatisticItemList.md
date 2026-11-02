# StatisticItemList — 통계 세부항목 목록

출처: [API개발명세서_통계세부항목목록.xls](API개발명세서_통계세부항목목록.xls)
원본 발간: 한국은행, 2025-03-26
추출일: 2026-04-28

## 기본 정보

| 항목 | 내용 |
|------|------|
| 서비스명 | StatisticItemList |
| 베이스 URL | https://ecos.bok.or.kr/api/ |
| 호출 방식 | PATH 기반 |
| 출력 형식 | XML, JSON |

## 요청 인자

| 항목명(국문) | 필수 | 샘플 | 설명 |
|------------|------|------|------|
| 서비스명 | Y | StatisticItemList | API 서비스명 |
| 인증키 | Y | sample | 인증키 |
| 요청유형 | Y | xml | xml, json |
| 언어구분 | Y | kr | kr/en |
| 요청시작건수 | Y | 1 | 시작 번호 |
| 요청종료건수 | Y | 10 | 끝 번호 |
| **통계표코드** | Y | 601Y002 | 통계표코드 (StatisticTableList에서 확보한 STAT_CODE) |

## 출력값

| 항목명(국문) | 항목명(영문) | 크기 | 샘플 | 설명 |
|------------|-------------|------|------|------|
| 통계표코드 | STAT_CODE | 8 | 601Y002 | 통계표코드 |
| 통계명 | STAT_NAME | 200 | 7.5.2. 지역별 소비유형별 개인 신용카드 | 통계명 |
| 항목그룹코드 | GRP_CODE | 20 | Group1 | 통계항목그룹코드 |
| 항목그룹명 | GRP_NAME | 60 | 지역코드 | 통계항목그룹명 |
| 통계항목코드 | ITEM_CODE | 20 | A | 통계항목코드 |
| 통계항목명 | ITEM_NAME | 200 | 서울 | 통계항목명 |
| 상위통계항목코드 | P_ITEM_CODE | 8 | null | 상위통계항목코드 |
| 상위통계항목명 | P_ITEM_NAME | 200 | null | 상위통계항목명 |
| 주기 | CYCLE | 2 | M | 주기 |
| 수록시작일자 | START_TIME | 8 | 200912 | 수록시작일자 |
| 수록종료일자 | END_TIME | 8 | 202112 | 수록종료일자 |
| 자료수 | DATA_CNT | 22 | 145 | 자료수 |
| 단위 | UNIT_NAME | 200 | 십억원 | 단위 |
| 가중치 | WEIGHT | 22 | null | 가중치 |

## 테스트 URL

```
https://ecos.bok.or.kr/api/StatisticItemList/sample/xml/kr/1/10/043Y070/
```

## 에러 코드 (공통)

[README.md](README.md#정본-에러-코드-6개-api-공통) 참조.
