# XBRL택사노미재무제표양식 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS003&apiId=2020001
추출일: 2026-04-28

## 기본 정보

| 메서드 | 요청URL | 인코딩 | 출력포멧 |
|--------|---------|--------|---------|
| GET | https://opendart.fss.or.kr/api/xbrlTaxonomy.json | UTF-8 | JSON |
| GET | https://opendart.fss.or.kr/api/xbrlTaxonomy.xml | UTF-8 | XML |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수여부 | 값설명 |
|--------|------|------|---------|--------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| sj_div | 재무제표구분 | STRING(5) | Y | 재무제표구분 코드 |

## 응답 결과

| 응답키 | 명칭 | 출력설명 |
|--------|------|---------|
| result.status | 에러 및 정보 코드 | 메시지 설명 참조 |
| result.message | 에러 및 정보 메시지 | 메시지 설명 참조 |
| list.sj_div | 재무제표구분 | 재무제표구분 |
| list.account_id | 계정 고유명칭 | 계정 고유명칭 |
| list.account_nm | 계정명 | 계정명 |
| list.bsns_de | 적용 기준일 | 적용 기준일 |
| list.label_kor | 한글 출력명 | 한글 출력명 |
| list.label_eng | 영문 출력명 | 영문 출력명 |
| list.data_tp | 데이터 유형 | 데이터 유형 |
| list.ifrs_ref | IFRS Reference | IFRS Reference |

## 에러 코드

| 코드 | 설명 |
|------|------|
| 000 | 정상 |
| 010 | 등록되지 않은 키입니다 |
| 013 | 조회된 데이타가 없습니다 |
| 100 | 필드의 부적절한 값입니다 |
| 900 | 정의되지 않은 오류가 발생하였습니다 |
