# 채권은행 등의 관리절차 개시 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020027
추출일: 2026-04-28

## 기본 정보

| 항목 | 내용 |
|------|------|
| 메서드 | GET |
| JSON URL | https://opendart.fss.or.kr/api/bnkMngtPcbg.json |
| XML URL | https://opendart.fss.or.kr/api/bnkMngtPcbg.xml |
| 인코딩 | UTF-8 |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수 | 설명 |
|--------|------|------|------|------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 40자리 인증키 |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사 고유번호(8자리) |
| bgn_de | 시작일 | STRING(8) | Y | 검색시작 접수일자(YYYYMMDD, 2015년 이후) |
| end_de | 종료일 | STRING(8) | Y | 검색종료 접수일자(YYYYMMDD, 2015년 이후) |

## 응답 결과

| 응답키 | 명칭 | 설명 |
|--------|------|------|
| result.status | 에러 및 정보 코드 | 메시지 설명 참조 |
| result.message | 에러 및 정보 메시지 | 메시지 설명 참조 |
| list.rcept_no | 접수번호 | 14자리 |
| list.corp_cls | 법인구분 | Y(유가), K(코스닥), N(코넥스), E(기타) |
| list.corp_code | 고유번호 | 8자리 |
| list.corp_name | 회사명 | 공시대상회사명 |
| list.mngt_pcbg_dd | 관리절차개시 결정일자 | 결정일자 |
| list.mngt_int | 관리기관 | 관리기관 정보 |
| list.mngt_pd | 관리기간 | 관리기간 |
| list.mngt_rs | 관리사유 | 관리사유 |
| list.cfd | 확인일자 | 확인일자 |

## 에러 코드

| 코드 | 의미 |
|------|------|
| 000 | 정상 |
| 010 | 등록되지 않은 키 |
| 013 | 조회된 데이타 없음 |
| 020 | 요청 제한 초과 |
| 100 | 필드의 부적절한 값 |
| 800 | 시스템 점검 중 |
