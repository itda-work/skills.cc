# 타법인 주식 및 출자증권 양수결정 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020046
추출일: 2026-04-28

## 기본 정보

| 메서드 | 요청URL | 인코딩 | 출력포멧 |
|--------|--------|--------|---------|
| GET | https://opendart.fss.or.kr/api/otcprStkInvscrInhDecsn.json | UTF-8 | JSON |
| GET | https://opendart.fss.or.kr/api/otcprStkInvscrInhDecsn.xml | UTF-8 | XML |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수여부 | 값설명 |
|--------|------|------|---------|--------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 고유번호(8자리) |
| bgn_de | 시작일(최초접수일) | STRING(8) | Y | 검색시작 접수일자(YYYYMMDD) |
| end_de | 종료일(최초접수일) | STRING(8) | Y | 검색종료 접수일자(YYYYMMDD) |

## 응답 결과

| 응답키 | 명칭 | 설명 |
|--------|------|------|
| rcept_no | 접수번호 | 접수번호(14자리) |
| corp_code | 고유번호 | 8자리 |
| corp_name | 회사명 | 공시대상회사명 |
| inhdtl_stkcnt | 양수내역(양수주식수) | 주식 수량 |
| inhdtl_inhprc | 양수내역(양수금액) | 거래금액(원) |
| atinh_eqrt | 양수후 지분비율 | 지분비율(%) |

## 에러 코드

| 코드 | 설명 |
|------|------|
| 000 | 정상 |
| 010 | 등록되지 않은 키입니다 |
| 013 | 조회된 데이타가 없습니다 |
| 020 | 요청 제한을 초과하였습니다 |
| 100 | 필드의 부적절한 값입니다 |
| 900 | 정의되지 않은 오류 |
