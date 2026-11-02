# 회사합병 결정 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020050
추출일: 2026-04-28

## 기본 정보

| 항목 | 내용 |
|------|------|
| 메서드 | GET |
| JSON URL | https://opendart.fss.or.kr/api/cmpMgDecsn.json |
| XML URL | https://opendart.fss.or.kr/api/cmpMgDecsn.xml |
| 인코딩 | UTF-8 |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수 | 값설명 |
|--------|------|------|------|--------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 고유번호(8자리) |
| bgn_de | 시작일 | STRING(8) | Y | 검색시작 접수일자(YYYYMMDD) |
| end_de | 종료일 | STRING(8) | Y | 검색종료 접수일자(YYYYMMDD) |

## 응답 결과

| 응답키 | 명칭 |
|--------|------|
| rcept_no | 접수번호(14자리) |
| corp_cls | 법인구분(Y/K/N/E) |
| corp_name | 회사명 |
| mg_mth | 합병방법 |
| mg_stn | 합병형태 |
| mgptncmp_cmpnm | 합병상대회사 명칭 |
| mgsc_mgdt | 합병기일 |
| aprskh_plnprc | 주식매수청구권 매수예정가격 |

## 에러 코드

| 코드 | 설명 |
|------|------|
| 000 | 정상 |
| 010 | 등록되지 않은 키입니다 |
| 013 | 조회된 데이타가 없습니다 |
| 020 | 요청 제한 초과(20,000건 이상) |
| 021 | 조회 회사 수 초과(최대 100건) |
| 100 | 부적절한 필드값 |
| 800 | 시스템 점검으로 인한 서비스가 중지 중입니다 |
