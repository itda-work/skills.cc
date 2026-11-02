# 단기사채 미상환 잔액 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2020005
추출일: 2026-04-28

## 기본 정보

| 메서드 | 요청URL | 인코딩 | 출력포멧 |
|--------|--------|--------|---------|
| GET | https://opendart.fss.or.kr/api/srtpdPsndbtNrdmpBlce.json | UTF-8 | JSON |
| GET | https://opendart.fss.or.kr/api/srtpdPsndbtNrdmpBlce.xml | UTF-8 | XML |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수여부 | 값설명 |
|--------|------|------|---------|--------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 고유번호(8자리) |
| bsns_year | 사업연도 | STRING(4) | Y | 사업연도(4자리, 2015년 이후) |
| reprt_code | 보고서 코드 | STRING(5) | Y | 11013(1분기), 11012(반기), 11014(3분기), 11011(사업보고서) |

## 응답 결과

| 응답키 | 명칭 | 출력설명 |
|--------|------|---------|
| result.status | 에러 및 정보 코드 | 메시지 설명 참조 |
| result.message | 에러 및 정보 메시지 | 메시지 설명 참조 |
| list.rcept_no | 접수번호 | 14자리 접수번호 |
| list.corp_cls | 법인구분 | Y(유가), K(코스닥), N(코넥스), E(기타) |
| list.corp_code | 고유번호 | 8자리 고유번호 |
| list.corp_name | 회사명 | 공시대상회사명 |
| list.de10_below | 10일 이하 | 금액 |
| list.de10_excess_de30_below | 10일초과 30일이하 | 금액 |
| list.de30_excess_de90_below | 30일초과 90일이하 | 금액 |
| list.de90_excess_de180_below | 90일초과 180일이하 | 금액 |
| list.de180_excess_yy1_below | 180일초과 1년이하 | 금액 |
| list.sm | 합계 | 금액 |
| list.stlm_dt | 결산기준일 | YYYY-MM-DD |

## 에러 코드

| 코드 | 메시지 |
|------|--------|
| 000 | 정상 |
| 010 | 등록되지 않은 키입니다 |
| 011 | 사용할 수 없는 키입니다 |
| 012 | 접근할 수 없는 IP입니다 |
| 013 | 조회된 데이타가 없습니다 |
| 020 | 요청 제한을 초과하였습니다 (20,000건 이상) |
| 100 | 필드의 부적절한 값입니다 |
