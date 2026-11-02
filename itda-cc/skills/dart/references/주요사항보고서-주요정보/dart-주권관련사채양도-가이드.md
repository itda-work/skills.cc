# 주권 관련 사채권 양도 결정 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020049
추출일: 2026-04-28

## 기본 정보

| 항목 | 내용 |
|------|------|
| 메서드 | GET |
| JSON URL | https://opendart.fss.or.kr/api/stkrtbdTrfDecsn.json |
| XML URL | https://opendart.fss.or.kr/api/stkrtbdTrfDecsn.xml |
| 인코딩 | UTF-8 |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수 | 설명 |
|--------|------|------|------|------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사 8자리 고유번호 |
| bgn_de | 시작일 | STRING(8) | Y | 검색시작 접수일자(YYYYMMDD); 2015년 이후 |
| end_de | 종료일 | STRING(8) | Y | 검색종료 접수일자(YYYYMMDD); 2015년 이후 |

## 응답 결과

응답 주요 필드: 접수번호, 법인구분, 회사명, 사채 종류, 양도일, 발행회사 정보, 양도내역(금액, 자산비율), 거래상대방, 외부평가, 이사회결의 정보.

## 에러 코드

| 코드 | 의미 |
|------|------|
| 000 | 정상 |
| 010 | 등록되지 않은 키입니다 |
| 013 | 조회된 데이터 없음 |
| 020 | 요청 제한 초과(20,000건 이상) |
| 100 | 필드의 부적절한 값 |
