# 감자 결정 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020026
추출일: 2026-04-28

## 기본 정보

| 항목 | 내용 |
|------|------|
| 메서드 | GET |
| JSON 엔드포인트 | https://opendart.fss.or.kr/api/crDecsn.json |
| XML 엔드포인트 | https://opendart.fss.or.kr/api/crDecsn.xml |
| 인코딩 | UTF-8 |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수 | 설명 |
|--------|------|------|------|------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 40자리 인증키 |
| corp_code | 고유번호 | STRING(8) | Y | 8자리 고유번호 |
| bgn_de | 시작일 | STRING(8) | Y | 검색시작 접수일자(YYYYMMDD); 2015년 이후 |
| end_de | 종료일 | STRING(8) | Y | 검색종료 접수일자(YYYYMMDD); 2015년 이후 |

## 응답 결과

| 응답키 | 설명 |
|--------|------|
| rcept_no | 접수번호(14자리) |
| corp_name | 회사명 |
| crstk_ostk_cnt | 감자주식의 종류와 수(보통주식 (주)) |
| fv_ps | 1주당 액면가액(원) |
| bfcr_cpt / atcr_cpt | 감자전·후 자본금 |
| cr_rt_ostk | 감자비율(보통주식 %) |
| cr_rs | 감자사유 |
| bddd | 이사회결의일 |

## 에러 코드

| 코드 | 의미 |
|------|------|
| 000 | 정상 |
| 010 | 등록되지 않은 키 |
| 013 | 조회된 데이타가 없음 |
| 020 | 요청 제한 초과(20,000건 이상) |
| 021 | 조회 회사 개수 초과(최대 100건) |
| 100 | 부적절한 필드 값 |
| 800 | 시스템 점검 중 |
