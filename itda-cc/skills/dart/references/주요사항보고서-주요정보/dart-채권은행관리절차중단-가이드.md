# 채권은행 등의 관리절차 중단 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020036
추출일: 2026-04-28

## 기본 정보

| 항목 | 내용 |
|------|------|
| 메서드 | GET |
| JSON URL | https://opendart.fss.or.kr/api/bnkMngtPcsp.json |
| XML URL | https://opendart.fss.or.kr/api/bnkMngtPcsp.xml |
| 인코딩 | UTF-8 |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수 | 설명 |
|--------|------|------|------|------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 고유번호(8자리) |
| bgn_de | 시작일 | STRING(8) | Y | YYYYMMDD 형식, 2015년 이후 |
| end_de | 종료일 | STRING(8) | Y | YYYYMMDD 형식, 2015년 이후 |

## 응답 결과

| 응답키 | 명칭 | 설명 |
|--------|------|------|
| result.status | 에러 코드 | 정상 또는 오류 코드 |
| result.message | 메시지 | 에러 및 정보 메시지 |
| list.rcept_no | 접수번호 | 14자리 접수번호 |
| list.corp_name | 회사명 | 공시대상회사명 |
| list.mngt_pcsp_dd | 중단 결정일 | 관리절차중단 결정일자 |
| list.sp_rs | 중단사유 | 중단 사유 |

## 에러 코드

| 코드 | 의미 |
|------|------|
| 000 | 정상 |
| 010 | 등록되지 않은 키입니다 |
| 013 | 조회된 데이타가 없습니다 |
| 020 | 요청 제한 초과 |
| 100 | 부적절한 필드 값 |
