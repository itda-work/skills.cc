# 대량보유 상황보고 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS004&apiId=2019021
추출일: 2026-04-28

## 기본 정보

| 메서드 | 요청URL | 인코딩 | 출력포멧 |
|--------|--------|--------|---------|
| GET | https://opendart.fss.or.kr/api/majorstock.json | UTF-8 | JSON |
| GET | https://opendart.fss.or.kr/api/majorstock.xml | UTF-8 | XML |

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
| list.rcept_dt | 공시 접수일자 | YYYYMMDD |
| list.corp_code | 고유번호 | 공시대상회사의 고유번호(8자리) |
| list.corp_name | 회사명 | 회사명 |
| list.report_tp | 주식등의 대량보유상황 보고구분 | 보고구분 |
| list.repror | 대표보고자 | 대표보고자 |
| list.stkqy | 보유주식등의 수 | 보유주식등의 수 |
| list.stkqy_irds | 보유주식등의 증감 | 증감 |
| list.stkrt | 보유비율 | 보유비율 |
| list.stkrt_irds | 보유비율 증감 | 증감 |
| list.ctr_stkqy | 주요체결 주식등의 수 | 주요체결 주식수 |
| list.ctr_stkrt | 주요체결 보유비율 | 주요체결 보유비율 |
| list.report_resn | 보고사유 | 보고사유 |

## 에러 코드

| 코드 | 설명 |
|------|------|
| 000 | 정상 |
| 010 | 등록되지 않은 키 |
| 013 | 조회된 데이타가 없음 |
| 020 | 요청 제한 초과 |
| 100 | 부적절한 필드 값 |
