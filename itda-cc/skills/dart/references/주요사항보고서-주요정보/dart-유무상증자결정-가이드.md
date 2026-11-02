# 유무상증자 결정 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020025
추출일: 2026-04-28

## 기본 정보

| 항목 | 내용 |
|------|------|
| 메서드 | GET |
| 요청 URL (JSON) | https://opendart.fss.or.kr/api/pifricDecsn.json |
| 요청 URL (XML) | https://opendart.fss.or.kr/api/pifricDecsn.xml |
| 인코딩 | UTF-8 |
| 출력포멧 | JSON, XML |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수여부 | 값설명 |
|--------|------|------|---------|--------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 고유번호(8자리) |
| bgn_de | 시작일(최초접수일) | STRING(8) | Y | 검색시작 접수일자(YYYYMMDD) |
| end_de | 종료일(최초접수일) | STRING(8) | Y | 검색종료 접수일자(YYYYMMDD) |

## 응답 결과

| 응답키 | 명칭 |
|--------|------|
| rcept_no | 접수번호(14자리) |
| corp_cls | 법인구분(Y/K/N/E) |
| corp_code | 고유번호(8자리) |
| corp_name | 회사명 |
| piic_nstk_ostk_cnt | 유상증자 신주 수(보통주식) |
| fric_nstk_ostk_cnt | 무상증자 신주 수(보통주식) |

## 에러 코드

| 코드 | 설명 |
|------|------|
| 000 | 정상 |
| 010 | 등록되지 않은 키 |
| 013 | 조회된 데이터 없음 |
| 020 | 요청 제한 초과 |
| 100 | 필드의 부적절한 값 |
| 900 | 정의되지 않은 오류 |
