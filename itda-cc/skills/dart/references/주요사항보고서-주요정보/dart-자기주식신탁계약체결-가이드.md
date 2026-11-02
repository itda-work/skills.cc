# 자기주식취득 신탁계약 체결 결정 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020040
추출일: 2026-04-28

## 기본 정보

| 항목 | 내용 |
|------|------|
| 메서드 | GET |
| JSON URL | https://opendart.fss.or.kr/api/tsstkAqTrctrCnsDecsn.json |
| XML URL | https://opendart.fss.or.kr/api/tsstkAqTrctrCnsDecsn.xml |
| 인코딩 | UTF-8 |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수 | 설명 |
|--------|------|------|------|------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사 고유번호(8자리) |
| bgn_de | 시작일 | STRING(8) | Y | 검색시작 접수일자(YYYYMMDD), 2015년 이후 정보제공 |
| end_de | 종료일 | STRING(8) | Y | 검색종료 접수일자(YYYYMMDD), 2015년 이후 정보제공 |

## 응답 결과

| 응답키 | 명칭 | 설명 |
|--------|------|------|
| result.status | 상태코드 | 에러 및 정보 코드 |
| list.rcept_no | 접수번호 | 14자리 접수번호 |
| list.corp_name | 회사명 | 공시대상회사명 |
| list.ctr_prc | 계약금액 | 원화 단위 금액 |
| list.ctr_pd_bgd | 계약기간(시작일) | - |
| list.ctr_pd_edd | 계약기간(종료일) | - |
| list.bddd | 이사회결의일 | 결정일 |

## 에러 코드

| 코드 | 메시지 |
|------|--------|
| 000 | 정상 |
| 010 | 등록되지 않은 키 |
| 013 | 조회된 데이터가 없음 |
| 020 | 요청 제한 초과 (20,000건 이상) |
| 100 | 필드의 부적절한 값 |
| 800 | 시스템 점검 중 |
| 900 | 정의되지 않은 오류 |
