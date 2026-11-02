# 직원 현황 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2019011
추출일: 2026-04-28

## 기본 정보

| 메서드 | 요청URL | 인코딩 | 출력포멧 |
|--------|---------|--------|---------|
| GET | https://opendart.fss.or.kr/api/empSttus.json | UTF-8 | JSON |
| GET | https://opendart.fss.or.kr/api/empSttus.xml | UTF-8 | XML |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수여부 | 값설명 |
|--------|------|------|---------|--------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 고유번호(8자리) |
| bsns_year | 사업연도 | STRING(4) | Y | 사업연도(4자리) ※ 2015년 이후 부터 정보제공 |
| reprt_code | 보고서 코드 | STRING(5) | Y | 1분기:11013, 반기:11012, 3분기:11014, 사업:11011 |

## 응답 결과

| 응답키 | 명칭 | 출력설명 |
|--------|------|---------|
| result.status | 에러 및 정보 코드 | 에러 및 정보 코드 |
| result.message | 에러 및 정보 메시지 | 에러 및 정보 메시지 |
| list.rcept_no | 접수번호 | 접수번호(14자리) |
| list.corp_cls | 법인구분 | Y(유가), K(코스닥), N(코넥스), E(기타) |
| list.corp_code | 고유번호 | 고유번호(8자리) |
| list.corp_name | 법인명 | 법인명 |
| list.fo_bbm | 사업부문 | 사업부문 |
| list.sexdstn | 성별 | 남/여 |
| list.rgllbr_co | 정규직 수 | 정규직 수 |
| list.cnttk_co | 계약직 수 | 계약직 수 |
| list.sm | 합계 | 합계 |
| list.fyer_salary_totamt | 연간 급여 총액 | 연간 급여 총액 |
| list.jan_salary_am | 1인평균 급여 액 | 1인평균 급여 액 |
| list.stlm_dt | 결산기준일 | YYYY-MM-DD |

## 에러 코드

| 코드 | 메시지 |
|------|--------|
| 000 | 정상 |
| 010 | 등록되지 않은 키 |
| 013 | 조회된 데이타가 없음 |
| 020 | 요청 제한 초과(20,000건 이상) |
| 100 | 필드의 부적절한 값 |
| 800 | 시스템 점검 중 |
| 900 | 정의되지 않은 오류 |
