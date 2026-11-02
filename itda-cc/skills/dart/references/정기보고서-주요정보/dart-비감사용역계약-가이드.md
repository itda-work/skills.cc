# 회계감사인과의 비감사용역 계약체결 현황 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2020011
추출일: 2026-04-28

## 기본 정보

| 메서드 | 요청URL | 인코딩 | 출력포멧 |
|--------|---------|--------|---------|
| GET | https://opendart.fss.or.kr/api/accnutAdtorNonAdtServcCnclsSttus.json | UTF-8 | JSON |
| GET | https://opendart.fss.or.kr/api/accnutAdtorNonAdtServcCnclsSttus.xml | UTF-8 | XML |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수여부 | 값설명 |
|---------|------|------|---------|---------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 고유번호(8자리) |
| bsns_year | 사업연도 | STRING(4) | Y | 사업연도(4자리), 2015년 이후 제공 |
| reprt_code | 보고서 코드 | STRING(5) | Y | 1분기:11013, 반기:11012, 3분기:11014, 사업보고서:11011 |

## 응답 결과

| 응답키 | 명칭 | 출력설명 |
|---------|------|---------|
| result.status | 에러 및 정보 코드 | 메시지 설명 참조 |
| result.message | 에러 및 정보 메시지 | 메시지 설명 참조 |
| list.rcept_no | 접수번호 | 14자리 접수번호 |
| list.corp_cls | 법인구분 | Y(유가), K(코스닥), N(코넥스), E(기타) |
| list.corp_code | 고유번호 | 8자리 고유번호 |
| list.corp_name | 회사명 | 공시대상회사명 |
| list.bsns_year | 사업연도 | 당기, 전기, 전전기 |
| list.cntrct_cncls_de | 계약체결일 | 계약체결 날짜 |
| list.servc_cn | 용역내용 | 용역 내용 |
| list.servc_exc_pd | 용역수행기간 | 수행 기간 |
| list.servc_mendng | 용역보수 | 보수액 |
| list.rm | 비고 | 비고사항 |
| list.stlm_dt | 결산기준일 | YYYY-MM-DD |

## 에러 코드

| 코드 | 메시지 |
|------|---------|
| 000 | 정상 |
| 010 | 등록되지 않은 키 |
| 011 | 사용할 수 없는 키 |
| 012 | 접근할 수 없는 IP |
| 013 | 조회된 데이터 없음 |
| 014 | 파일이 존재하지 않음 |
| 020 | 요청 제한 초과 (20,000건 이상) |
| 021 | 조회 가능한 회사 개수 초과 (최대 100건) |
| 100 | 필드의 부적절한 값 |
| 101 | 부적절한 접근 |
| 800 | 시스템 점검 중 |
| 900 | 정의되지 않은 오류 |
| 901 | 사용자 계정의 개인정보 보유기간 만료 |
