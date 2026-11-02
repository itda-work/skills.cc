# 최대주주 현황 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2019007
추출일: 2026-04-28

## 기본 정보

| 메서드 | 요청URL | 인코딩 | 출력포멧 |
|--------|---------|--------|---------|
| GET | https://opendart.fss.or.kr/api/hyslrSttus.json | UTF-8 | JSON |
| GET | https://opendart.fss.or.kr/api/hyslrSttus.xml | UTF-8 | XML |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수여부 | 값설명 |
|--------|------|------|---------|--------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 고유번호(8자리) |
| bsns_year | 사업연도 | STRING(4) | Y | 사업연도(4자리) ※ 2015년 이후 부터 정보제공 |
| reprt_code | 보고서 코드 | STRING(5) | Y | 1분기: 11013 / 반기: 11012 / 3분기: 11014 / 사업: 11011 |

## 응답 결과

| 응답키 | 명칭 | 출력설명 |
|--------|------|----------|
| result.status | 에러 및 정보 코드 | 메시지 설명 참조 |
| result.message | 에러 및 정보 메시지 | 메시지 설명 참조 |
| list.rcept_no | 접수번호 | 접수번호(14자리) |
| list.corp_cls | 법인구분 | Y(유가), K(코스닥), N(코넥스), E(기타) |
| list.corp_code | 고유번호 | 고유번호(8자리) |
| list.corp_name | 법인명 | 법인명 |
| list.nm | 성명 | 성명 |
| list.relate | 관계 | 본인, 친인척 등 |
| list.stock_knd | 주식 종류 | 주식 종류 |
| list.bsis_posesn_stock_co | 기초 소유 주식 수 | 기초 소유 주식 수 |
| list.bsis_posesn_stock_qota_rt | 기초 소유 주식 지분율 | 기초 소유 주식 지분율 |
| list.trmend_posesn_stock_co | 기말 소유 주식 수 | 기말 소유 주식 수 |
| list.trmend_posesn_stock_qota_rt | 기말 소유 주식 지분율 | 기말 소유 주식 지분율 |
| list.rm | 비고 | 비고 |
| list.stlm_dt | 결산기준일 | YYYY-MM-DD |

## 에러 코드

| 코드 | 메시지 |
|------|--------|
| 000 | 정상 |
| 010 | 등록되지 않은 키 |
| 011 | 사용할 수 없는 키 |
| 012 | 접근할 수 없는 IP |
| 013 | 조회된 데이터 없음 |
| 020 | 요청 제한 초과(20,000건 이상) |
| 100 | 필드의 부적절한 값 |
| 800 | 시스템 점검 중 |
| 900 | 정의되지 않은 오류 |
