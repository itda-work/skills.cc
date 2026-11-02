# 신주인수권부사채권 발행결정 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020034
추출일: 2026-04-28

## 기본 정보

| 항목 | 내용 |
|------|------|
| 메서드 | GET |
| JSON URL | https://opendart.fss.or.kr/api/bdwtIsDecsn.json |
| XML URL | https://opendart.fss.or.kr/api/bdwtIsDecsn.xml |
| 인코딩 | UTF-8 |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수 | 설명 |
|--------|------|------|------|------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 고유번호(8자리) |
| bgn_de | 시작일 | STRING(8) | Y | 접수일자(YYYYMMDD) |
| end_de | 종료일 | STRING(8) | Y | 접수일자(YYYYMMDD) |

## 응답 결과

| 응답키 | 명칭 | 설명 |
|--------|------|------|
| result.status | 에러 코드 | 처리 상태 코드 |
| list.rcept_no | 접수번호 | 14자리 |
| list.corp_name | 회사명 | 공시대상회사명 |
| list.bd_fta | 사채총액 | 원화 단위 |
| list.ex_prc | 행사가액 | 원/주 단위 |

## 에러 코드

| 코드 | 메시지 |
|------|--------|
| 000 | 정상 |
| 013 | 조회된 데이타가 없습니다 |
| 020 | 요청 제한 초과(20,000건 이상) |
| 100 | 필드의 부적절한 값 |
| 901 | 개인정보 보유기간 만료로 사용 불가 |
