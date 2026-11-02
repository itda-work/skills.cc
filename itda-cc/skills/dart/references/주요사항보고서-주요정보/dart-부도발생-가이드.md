# 부도발생 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020019
추출일: 2026-04-28

## 기본 정보

| 메서드 | 요청URL | 인코딩 | 출력포멧 |
|--------|---------|--------|---------|
| GET | https://opendart.fss.or.kr/api/dfOcr.json | UTF-8 | JSON |
| GET | https://opendart.fss.or.kr/api/dfOcr.xml | UTF-8 | XML |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수여부 | 값설명 |
|--------|------|------|---------|--------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 고유번호(8자리) |
| bgn_de | 시작일(최초접수일) | STRING(8) | Y | 검색시작 접수일자(YYYYMMDD) ※ 2015년 이후 |
| end_de | 종료일(최초접수일) | STRING(8) | Y | 검색종료 접수일자(YYYYMMDD) ※ 2015년 이후 |

## 응답 결과

| 응답키 | 명칭 | 출력설명 |
|--------|------|---------|
| result.status | 에러 및 정보 코드 | 메시지 설명 참조 |
| result.message | 에러 및 정보 메시지 | 메시지 설명 참조 |
| list.rcept_no | 접수번호 | 접수번호(14자리) |
| list.corp_cls | 법인구분 | Y(유가), K(코스닥), N(코넥스), E(기타) |
| list.corp_code | 고유번호 | 고유번호(8자리) |
| list.corp_name | 공시대상회사명 | 공시대상회사명 |
| list.df_cn | 부도내용 | 부도내용 |
| list.df_amt | 부도금액 | 부도금액 |
| list.df_bnk | 부도발생은행 | 부도발생은행 |
| list.dfd | 최종부도(당좌거래정지)일자 | 최종부도일자 |
| list.df_rs | 부도사유 및 경위 | 부도사유 및 경위 |

## 에러 코드

| 코드 | 메시지 |
|------|--------|
| 000 | 정상 |
| 010 | 등록되지 않은 키 |
| 013 | 조회된 데이터 없음 |
| 100 | 필드의 부적절한 값 |
| 901 | 개인정보 보유기간 만료 |
