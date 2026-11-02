# 배당에 관한 사항 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2019005
추출일: 2026-04-28

## 기본 정보

| 메서드 | 요청URL | 인코딩 | 출력포멧 |
|--------|--------|--------|--------|
| GET | https://opendart.fss.or.kr/api/alotMatter.json | UTF-8 | JSON |
| GET | https://opendart.fss.or.kr/api/alotMatter.xml | UTF-8 | XML |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수여부 | 값설명 |
|--------|------|------|---------|--------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 고유번호(8자리) |
| bsns_year | 사업연도 | STRING(4) | Y | 사업연도(4자리) ※ 2015년 이후 정보제공 |
| reprt_code | 보고서 코드 | STRING(5) | Y | 11013(1분기), 11012(반기), 11014(3분기), 11011(사업보고서) |

## 응답 결과

| 응답키 | 명칭 | 출력설명 |
|--------|------|---------|
| result.status | 에러 및 정보 코드 | 메시지 설명 참조 |
| result.message | 에러 및 정보 메시지 | 메시지 설명 참조 |
| list.rcept_no | 접수번호 | 14자리 접수번호 |
| list.corp_cls | 법인구분 | Y(유가), K(코스닥), N(코넥스), E(기타) |
| list.corp_code | 고유번호 | 8자리 고유번호 |
| list.corp_name | 법인명 | 법인명 |
| list.se | 구분 | 유상증자(주주배정), 전환권행사 등 |
| list.stock_knd | 주식 종류 | 보통주 등 |
| list.thstrm | 당기 | 수치값 |
| list.frmtrm | 전기 | 수치값 |
| list.lwfr | 전전기 | 수치값 |
| list.stlm_dt | 결산기준일 | YYYY-MM-DD |

## 에러 코드

| 코드 | 설명 |
|------|------|
| 000 | 정상 |
| 010 | 등록되지 않은 키 |
| 011 | 사용할 수 없는 키 |
| 012 | 접근할 수 없는 IP |
| 013 | 조회된 데이터가 없음 |
| 020 | 요청 제한 초과 (20,000건 이상) |
| 100 | 필드의 부적절한 값 |
| 800 | 시스템 점검 중 |
| 900 | 정의되지 않은 오류 |
