# 자기주식취득 신탁계약 해지 결정 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020041
추출일: 2026-04-28

## 기본 정보

| 항목 | 내용 |
|------|------|
| 메서드 | GET |
| JSON URL | https://opendart.fss.or.kr/api/tsstkAqTrctrCcDecsn.json |
| XML URL | https://opendart.fss.or.kr/api/tsstkAqTrctrCcDecsn.xml |
| 인코딩 | UTF-8 |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수 | 설명 |
|--------|------|------|------|------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사 고유번호 |
| bgn_de | 시작일 | STRING(8) | Y | 검색시작 접수일자(YYYYMMDD) |
| end_de | 종료일 | STRING(8) | Y | 검색종료 접수일자(YYYYMMDD) |

## 응답 결과

| 응답키 | 명칭 | 설명 |
|--------|------|------|
| rcept_no | 접수번호 | 접수번호(14자리) |
| corp_name | 회사명 | 공시대상회사명 |
| ctr_prc_bfcc | 계약금액(해지 전) | 원 단위 |
| ctr_prc_atcc | 계약금액(해지 후) | 원 단위 |
| cc_pp | 해지목적 | 해지목적 정보 |
| bddd | 이사회결의일 | 결정일자 |

## 에러 코드

| 코드 | 설명 |
|------|------|
| 000 | 정상 |
| 010 | 등록되지 않은 키 |
| 013 | 조회된 데이타가 없습니다 |
| 020 | 요청 제한 초과(20,000건 이상) |
| 100 | 필드의 부적절한 값 |
| 800 | 시스템 점검 중 |
| 900 | 정의되지 않은 오류 |
