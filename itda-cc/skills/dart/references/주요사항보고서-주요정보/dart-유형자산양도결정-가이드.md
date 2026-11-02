# 유형자산 양도 결정 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020045
추출일: 2026-04-28

## 기본 정보

| 항목 | 내용 |
|------|------|
| 메서드 | GET |
| JSON URL | https://opendart.fss.or.kr/api/tgastTrfDecsn.json |
| XML URL | https://opendart.fss.or.kr/api/tgastTrfDecsn.xml |
| 인코딩 | UTF-8 |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수 | 설명 |
|--------|------|------|------|------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 8자리 고유번호 |
| bgn_de | 시작일 | STRING(8) | Y | 검색시작일(YYYYMMDD); 2015년 이후 |
| end_de | 종료일 | STRING(8) | Y | 검색종료일(YYYYMMDD); 2015년 이후 |

## 응답 결과

| 응답키 | 설명 |
|--------|------|
| rcept_no | 접수번호(14자리) |
| corp_name | 회사명 |
| ast_nm | 자산명 |
| trfdtl_trfprc | 양도금액(원) |
| dlptn_cmpnm | 거래상대방 회사명 |
| bddd | 이사회결의일 |

## 에러 코드

| 코드 | 메시지 |
|------|--------|
| 000 | 정상 |
| 010 | 등록되지 않은 키 |
| 013 | 조회된 데이터 없음 |
| 020 | 요청 제한 초과 |
| 100 | 필드의 부적절한 값 |
| 900 | 정의되지 않은 오류 |
