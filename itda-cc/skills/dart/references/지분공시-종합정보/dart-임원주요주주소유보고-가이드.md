# 임원·주요주주 소유보고 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS004&apiId=2019022
추출일: 2026-04-28

## 기본 정보

| 메서드 | 요청URL | 인코딩 | 출력포멧 |
|--------|--------|--------|---------|
| GET | https://opendart.fss.or.kr/api/elestock.json | UTF-8 | JSON |
| GET | https://opendart.fss.or.kr/api/elestock.xml | UTF-8 | XML |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수여부 | 값설명 |
|--------|------|------|---------|--------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 고유번호(8자리) |

## 응답 결과

| 응답키 | 명칭 | 출력설명 |
|--------|------|---------|
| result.status | 에러 및 정보 코드 | 메시지 설명 참조 |
| result.message | 에러 및 정보 메시지 | 메시지 설명 참조 |
| list.rcept_no | 접수번호 | 접수번호(14자리) |
| list.rcept_dt | 접수일자 | YYYY-MM-DD |
| list.corp_code | 고유번호 | 공시대상회사의 고유번호(8자리) |
| list.corp_name | 회사명 | 회사명 |
| list.repror | 보고자 | 보고자명 |
| list.sp_stock_lmp_cnt | 특정 증권 등 소유 수 | 9,999,999,999 |
| list.sp_stock_lmp_rate | 특정 증권 등 소유 비율 | 0.00 |

## 에러 코드

| 코드 | 메시지 |
|------|--------|
| 000 | 정상 |
| 010 | 등록되지 않은 키입니다 |
| 013 | 조회된 데이타가 없습니다 |
| 020 | 요청 제한을 초과하였습니다 |
| 100 | 필드의 부적절한 값입니다 |
| 800 | 시스템 점검으로 인한 서비스가 중지 중입니다 |
