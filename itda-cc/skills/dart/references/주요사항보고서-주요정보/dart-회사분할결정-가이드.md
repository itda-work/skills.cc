# 회사분할 결정 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020051
추출일: 2026-04-28

## 기본 정보

| 구분 | 내용 |
|------|------|
| 메서드 | GET |
| 요청 URL (JSON) | https://opendart.fss.or.kr/api/cmpDvDecsn.json |
| 요청 URL (XML) | https://opendart.fss.or.kr/api/cmpDvDecsn.xml |
| 인코딩 | UTF-8 |
| 출력포멧 | JSON, XML |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수여부 | 값설명 |
|--------|------|------|---------|--------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 고유번호(8자리) |
| bgn_de | 시작일 | STRING(8) | Y | 검색시작 접수일자(YYYYMMDD, 2015년 이후) |
| end_de | 종료일 | STRING(8) | Y | 검색종료 접수일자(YYYYMMDD, 2015년 이후) |

## 응답 결과

| 응답키 | 명칭 | 설명 |
|--------|------|------|
| result.status | 에러 및 정보 코드 | - |
| result.message | 에러 및 정보 메시지 | - |
| list.rcept_no | 접수번호 | 14자리 |
| list.corp_name | 회사명 | 공시대상회사명 |
| list.dv_mth | 분할방법 | 분할방법 |
| list.dv_rt | 분할비율 | 분할비율 |
| list.atdv_excmp_cmpnm | 분할 후 존속회사명 | 존속회사명 |
| list.dvfcmp_cmpnm | 분할설립회사명 | 분할설립회사명 |
| list.dvdt | 분할기일 | 분할기일 |

## 에러 코드

| 코드 | 메시지 |
|------|--------|
| 000 | 정상 |
| 010 | 등록되지 않은 키 |
| 013 | 조회된 데이타가 없습니다 |
| 020 | 요청 제한 초과 |
| 100 | 필드의 부적절한 값 |
| 900 | 정의되지 않은 오류 |
