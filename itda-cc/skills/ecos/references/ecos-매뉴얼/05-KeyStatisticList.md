# KeyStatisticList — 100대 통계지표

출처: [API개발명세서_100대.xls](API개발명세서_100대.xls)
원본 발간: 한국은행, 2025-03-26
추출일: 2026-04-28

## 기본 정보

| 항목 | 내용 |
|------|------|
| 서비스명 | KeyStatisticList |
| 베이스 URL | https://ecos.bok.or.kr/api/ |
| 호출 방식 | PATH 기반 |
| 출력 형식 | XML, JSON |

한국은행이 선정한 핵심 경제지표 약 100종을 한 번에 조회. 제안서에서 경제 환경 개요에 유용.

## 요청 인자

| 항목명(국문) | 필수 | 샘플 | 설명 |
|------------|------|------|------|
| 서비스명 | Y | KeyStatisticList | API 서비스명 |
| 인증키 | Y | sample | 인증키 |
| 요청유형 | Y | xml | xml, json |
| 언어구분 | Y | kr | kr/en |
| 요청시작건수 | Y | 1 | 시작 번호 |
| 요청종료건수 | Y | 10 | 끝 번호 |

> 추가 파라미터 없음 — 6개 공통 인자만 사용.

## 출력값

| 항목명(국문) | 항목명(영문) | 크기 | 샘플 | 설명 |
|------------|-------------|------|------|------|
| 통계그룹명 | CLASS_NAME | 400 | 국민소득 · 경기 · 기업경영 | 통계그룹명 |
| 통계명 | KEYSTAT_NAME | 200 | 경제성장률(전기대비) | 통계명 |
| 값 | DATA_VALUE | 23 | 1.9 | 값 |
| 시점 | CYCLE | 13 | 202003 | 통계의 최근 수록 시점 |
| 단위 | UNIT_NAME | 200 | %, 달러, 십억원 등 | 단위 |

> **주의**: 다른 API에서는 `CYCLE`이 주기 코드(A/Q/M)를 의미하지만, KeyStatisticList의 `CYCLE`은 **시점 값**(예: 202003 = 2020년 3월)을 담는다. 매뉴얼 표기 차이.

## 테스트 URL

```
https://ecos.bok.or.kr/api/KeyStatisticList/sample/xml/kr/1/10
```

## 에러 코드 (공통)

[README.md](README.md#정본-에러-코드-6개-api-공통) 참조.

## 코드 사용 관점

`ecos_api.py:get_key_statistics()` 함수가 이 endpoint 사용.
