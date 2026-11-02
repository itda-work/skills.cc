# 주식교환·이전 결정 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020053
추출일: 2026-04-28

## 기본 정보

| 메서드 | 요청URL | 인코딩 | 출력포멧 |
|--------|---------|--------|---------|
| GET | https://opendart.fss.or.kr/api/stkExtrDecsn.json | UTF-8 | JSON |
| GET | https://opendart.fss.or.kr/api/stkExtrDecsn.xml | UTF-8 | XML |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수여부 | 값설명 |
|--------|------|------|---------|--------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 고유번호(8자리) |
| bgn_de | 시작일 | STRING(8) | Y | 검색시작 접수일자(YYYYMMDD) |
| end_de | 종료일 | STRING(8) | Y | 검색종료 접수일자(YYYYMMDD) |

## 응답 결과

| 응답키 | 명칭 | 설명 |
|--------|------|------|
| rcept_no | 접수번호 | 접수번호(14자리) |
| corp_name | 회사명 | 공시대상회사명 |
| extr_stn | 교환·이전 형태 | 교환·이전 형태 |
| extr_tgcmp_cmpnm | 대상법인명 | 교환·이전 대상법인(회사명) |
| extr_rt | 교환·이전 비율 | 교환·이전 비율 |
| bddd | 이사회결의일 | 이사회결의일(결정일) |

## 에러 코드

| 코드 | 메시지 |
|------|--------|
| 000 | 정상 |
| 010 | 등록되지 않은 키입니다 |
| 013 | 조회된 데이타가 없습니다 |
| 020 | 요청 제한 초과 |
| 100 | 필드의 부적절한 값 |
| 900 | 정의되지 않은 오류 |
