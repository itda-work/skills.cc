# 해외 증권시장 주권등 상장 결정 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020029
추출일: 2026-04-28

## 기본 정보

| 항목 | 설명 |
|------|------|
| 메서드 | GET |
| JSON 엔드포인트 | https://opendart.fss.or.kr/api/ovLstDecsn.json |
| XML 엔드포인트 | https://opendart.fss.or.kr/api/ovLstDecsn.xml |
| 인코딩 | UTF-8 |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수 | 설명 |
|--------|------|------|------|------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 40자리 인증키 |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 8자리 고유번호 |
| bgn_de | 시작일 | STRING(8) | Y | 검색 시작 접수일(YYYYMMDD, 2015년 이후) |
| end_de | 종료일 | STRING(8) | Y | 검색 종료 접수일(YYYYMMDD, 2015년 이후) |

## 응답 결과

주요 필드:
- rcept_no: 14자리 접수번호
- corp_cls: 법인구분(Y/K/N/E)
- corp_code/corp_name: 고유번호 및 회사명
- lstprstk_ostk_cnt/lstprstk_estk_cnt: 상장예정주식 수(보통/기타)
- tisstk_ostk/tisstk_estk: 발행주식 총수
- lstex_nt: 상장거래소(소재국가)
- lstpp: 해외상장목적
- lstprd: 상장예정일자
- bddd: 이사회결의일

## 에러 코드

| 코드 | 설명 |
|------|------|
| 000 | 정상 |
| 010 | 등록되지 않은 키 |
| 013 | 조회된 데이터 없음 |
| 020 | 요청 제한 초과 |
| 100 | 부적절한 필드값 |
| 800 | 시스템 점검 중 |
