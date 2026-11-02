# 전환사채권 발행결정 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020033
추출일: 2026-04-28

## 기본 정보

| 메서드 | 요청URL | 인코딩 | 출력포멧 |
|--------|---------|--------|---------|
| GET | https://opendart.fss.or.kr/api/cvbdIsDecsn.json | UTF-8 | JSON |
| GET | https://opendart.fss.or.kr/api/cvbdIsDecsn.xml | UTF-8 | XML |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수여부 | 값설명 |
|--------|------|------|---------|--------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사 고유번호(8자리) |
| bgn_de | 시작일 | STRING(8) | Y | 검색시작 접수일자(YYYYMMDD) |
| end_de | 종료일 | STRING(8) | Y | 검색종료 접수일자(YYYYMMDD) |

## 응답 결과

응답에는 접수번호, 회사정보, 사채 조건(권면총액, 이자율, 만기일), 전환 관련 사항(전환비율, 전환가액, 청구기간), 합병 관련 정보 등이 포함된다.

주요 필드: rcept_no, corp_cls, corp_code, corp_name, bd_tm(사채의 종류/회차), bd_fta(사채권면총액), bd_intr_ex(이자율), bd_mtd(사채만기일), cv_rt(전환비율), cv_prc(전환가액), cv_rqsr_pd(전환청구기간), bddd(이사회결의일).

## 에러 코드

| 코드 | 설명 |
|------|------|
| 000 | 정상 |
| 010 | 등록되지 않은 키입니다 |
| 013 | 조회된 데이타가 없습니다 |
| 020 | 요청 제한 초과 |
| 100 | 필드의 부적절한 값 |
