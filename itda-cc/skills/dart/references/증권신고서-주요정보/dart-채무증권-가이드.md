# 채무증권 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS006&apiId=2020055
추출일: 2026-04-28

## 기본 정보

| 구분 | 내용 |
|------|------|
| 메서드 | GET |
| 요청URL (JSON) | https://opendart.fss.or.kr/api/bdRs.json |
| 요청URL (XML) | https://opendart.fss.or.kr/api/bdRs.xml |
| 인코딩 | UTF-8 |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수 | 설명 |
|--------|------|------|------|------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 고유번호(8자리) |
| bgn_de | 시작일 | STRING(8) | Y | 검색시작 접수일자(YYYYMMDD), 2015년 이후 정보 |
| end_de | 종료일 | STRING(8) | Y | 검색종료 접수일자(YYYYMMDD), 2015년 이후 정보 |

## 응답 결과

| 응답키 | 설명 |
|--------|------|
| result.status | 에러 및 정보 코드 |
| result.message | 에러 및 정보 메시지 |
| list.corp_name | 공시대상회사명 |
| list.bdnmn | 채무증권 명칭 |
| list.slmth | 모집(매출)방법 |
| list.intr | 이자율 |
| list.rpd | 상환기일 |

## 에러 코드

| 코드 | 메시지 |
|------|--------|
| 000 | 정상 |
| 010 | 등록되지 않은 키입니다 |
| 013 | 조회된 데이타가 없습니다 |
| 020 | 요청 제한 초과 (20,000건 이상) |
| 021 | 조회 가능 회사 개수 초과(최대 100건) |
| 100 | 필드의 부적절한 값 |
