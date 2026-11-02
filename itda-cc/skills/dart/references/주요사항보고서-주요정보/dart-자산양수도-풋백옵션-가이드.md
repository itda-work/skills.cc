# 자산양수도(기타), 풋백옵션 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020018
추출일: 2026-04-28

## 기본 정보

| 메서드 | 요청URL | 인코딩 | 출력포멧 |
|--------|--------|--------|--------|
| GET | https://opendart.fss.or.kr/api/astInhtrfEtcPtbkOpt.json | UTF-8 | JSON |
| GET | https://opendart.fss.or.kr/api/astInhtrfEtcPtbkOpt.xml | UTF-8 | XML |

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
| list.corp_code | 고유번호 | 공시대상회사의 고유번호(8자리) |
| list.corp_name | 공시대상회사명 | 공시대상회사명 |
| list.rp_rsn | 보고 사유 | 보고 사유 |
| list.ast_inhtrf_prc | 자산양수ㆍ도 가액 | 자산양수도 가액 |

## 에러 코드

| 코드 | 메시지 |
|------|--------|
| 000 | 정상 |
| 010 | 등록되지 않은 키입니다. |
| 011 | 사용할 수 없는 키입니다. |
| 012 | 접근할 수 없는 IP입니다. |
| 013 | 조회된 데이타가 없습니다. |
| 020 | 요청 제한을 초과하였습니다. |
| 100 | 필드의 부적절한 값입니다. |
| 901 | 사용자 계정의 개인정보 보유기간이 만료되어 사용할 수 없는 키입니다. |
