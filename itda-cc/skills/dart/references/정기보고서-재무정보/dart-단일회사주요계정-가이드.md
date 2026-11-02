# 단일회사 주요계정 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS003&apiId=2019016
추출일: 2026-04-28

## 기본 정보

| 메서드 | 요청URL | 인코딩 | 출력포멧 |
|--------|--------|--------|---------|
| GET | https://opendart.fss.or.kr/api/fnlttSinglAcnt.json | UTF-8 | JSON |
| GET | https://opendart.fss.or.kr/api/fnlttSinglAcnt.xml | UTF-8 | XML |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수여부 | 값설명 |
|--------|------|------|---------|--------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 고유번호(8자리) |
| bsns_year | 사업연도 | STRING(4) | Y | 사업연도(4자리) ※ 2015년 이후 부터 정보제공 |
| reprt_code | 보고서 코드 | STRING(5) | Y | 1분기: 11013 / 반기: 11012 / 3분기: 11014 / 사업보고서: 11011 |

## 응답 결과

| 응답키 | 명칭 | 출력설명 |
|--------|------|---------|
| result.status | 에러 및 정보 코드 | 메시지 설명 참조 |
| result.message | 에러 및 정보 메시지 | 메시지 설명 참조 |
| list.rcept_no | 접수번호 | 접수번호(14자리) |
| list.bsns_year | 사업 연도 | 2019 |
| list.stock_code | 종목 코드 | 상장회사의 종목코드(6자리) |
| list.reprt_code | 보고서 코드 | 1분기보고서 등 |
| list.account_nm | 계정명 | ex) 자본총계 |
| list.fs_div | 개별/연결구분 | OFS:재무제표, CFS:연결재무제표 |
| list.thstrm_amount | 당기금액 | 9,999,999,999 |
| list.frmtrm_amount | 전기금액 | 9,999,999,999 |

## 에러 코드

| 코드 | 메시지 |
|------|--------|
| 000 | 정상 |
| 010 | 등록되지 않은 키입니다 |
| 013 | 조회된 데이타가 없습니다 |
| 020 | 요청 제한을 초과하였습니다 |
| 100 | 필드의 부적절한 값입니다 |
| 800 | 시스템 점검으로 인한 서비스가 중지 중입니다 |
| 900 | 정의되지 않은 오류가 발생하였습니다 |
