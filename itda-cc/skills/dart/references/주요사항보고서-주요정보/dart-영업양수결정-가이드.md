# 영업양수 결정 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020042
추출일: 2026-04-28

## 기본 정보

| 메서드 | 요청 URL | 인코딩 | 포멧 |
|--------|---------|--------|------|
| GET | https://opendart.fss.or.kr/api/bsnInhDecsn.json | UTF-8 | JSON |
| GET | https://opendart.fss.or.kr/api/bsnInhDecsn.xml | UTF-8 | XML |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수 | 설명 |
|--------|------|------|------|------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키 |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 고유번호 |
| bgn_de | 시작일 | STRING(8) | Y | 검색시작 접수일자(YYYYMMDD) |
| end_de | 종료일 | STRING(8) | Y | 검색종료 접수일자(YYYYMMDD) |

## 응답 결과

| 응답키 | 명칭 | 설명 |
|--------|------|------|
| rcept_no | 접수번호 | 14자리 |
| corp_name | 회사명 | 공시대상회사명 |
| inh_bsn | 양수영업 | 양수영업 내용 |
| inh_prc | 양수가액 | 원 단위 금액 |
| ast_inh_bsn | 자산액(양수대상) | 원 단위 금액 |
| dlptn_cmpnm | 거래상대방 | 회사명 또는 성명 |
| bddd | 이사회결의일 | 결정일 |

## 에러 코드

| 코드 | 메시지 |
|------|--------|
| 000 | 정상 |
| 010 | 등록되지 않은 키 |
| 013 | 조회된 데이타가 없습니다 |
| 020 | 요청 제한 초과 |
| 100 | 필드의 부적절한 값 |
| 900 | 정의되지 않은 오류 |
