# 유상증자 결정 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020023
추출일: 2026-04-28

## 기본 정보

| 항목 | 내용 |
|------|------|
| 메서드 | GET |
| 요청URL (JSON) | https://opendart.fss.or.kr/api/piicDecsn.json |
| 요청URL (XML) | https://opendart.fss.or.kr/api/piicDecsn.xml |
| 인코딩 | UTF-8 |
| 출력포멧 | JSON, XML |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수여부 | 값설명 |
|--------|------|------|---------|--------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 고유번호(8자리) |
| bgn_de | 시작일(최초접수일) | STRING(8) | Y | 검색시작 접수일자(YYYYMMDD) ※ 2015년 이후 부터 정보제공 |
| end_de | 종료일(최초접수일) | STRING(8) | Y | 검색종료 접수일자(YYYYMMDD) ※ 2015년 이후 부터 정보제공 |

## 응답 결과

| 응답키 | 명칭 | 출력설명 |
|--------|------|---------|
| result.status | 에러 및 정보 코드 | 메시지 설명 참조 |
| result.message | 에러 및 정보 메시지 | 메시지 설명 참조 |
| list.rcept_no | 접수번호 | 접수번호(14자리) |
| list.corp_cls | 법인구분 | Y(유가), K(코스닥), N(코넥스), E(기타) |
| list.corp_code | 고유번호 | 고유번호(8자리) |
| list.corp_name | 공시대상회사명 | 공시대상회사명 |
| list.nstk_ostk_cnt | 신주의 종류와 수(보통주식) | 보통주식 수 |
| list.fv_ps | 1주당 액면가액(원) | 액면가액 |
| list.fdpp_fclt | 자금조달목적(시설자금) | 자금조달목적 |
| list.ic_mthn | 증자방식 | 증자방식 |

## 에러 코드

| 코드 | 메시지 |
|------|--------|
| 000 | 정상 |
| 010 | 등록되지 않은 키 |
| 013 | 조회된 데이타가 없음 |
| 020 | 요청 제한 초과(20,000건 이상) |
| 100 | 부적절한 필드값 |
| 800 | 시스템 점검 중 |
