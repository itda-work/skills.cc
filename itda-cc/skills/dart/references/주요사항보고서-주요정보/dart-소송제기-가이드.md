# 소송 등의 제기 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020028
추출일: 2026-04-28

## 기본 정보

| 항목 | 내용 |
|------|------|
| 메서드 | GET |
| JSON 요청URL | https://opendart.fss.or.kr/api/lwstLg.json |
| XML 요청URL | https://opendart.fss.or.kr/api/lwstLg.xml |
| 인코딩 | UTF-8 |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수 | 설명 |
|--------|------|------|------|------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 고유번호(8자리) |
| bgn_de | 시작일 | STRING(8) | Y | 검색시작 접수일자(YYYYMMDD) ※ 2015년 이후 |
| end_de | 종료일 | STRING(8) | Y | 검색종료 접수일자(YYYYMMDD) ※ 2015년 이후 |

## 응답 결과

| 응답키 | 설명 |
|--------|------|
| rcept_no | 접수번호(14자리) |
| corp_cls | 법인구분(Y/K/N/E) |
| corp_name | 회사명 |
| icnm | 사건의 명칭 |
| ac_ap | 원고·신청인 |
| rq_cn | 청구내용 |
| cpct | 관할법원 |
| ft_ctp | 향후대책 |

## 에러 코드

| 코드 | 의미 |
|------|------|
| 000 | 정상 |
| 010 | 등록되지 않은 키 |
| 013 | 조회된 데이타가 없습니다 |
| 020 | 요청 제한 초과 |
| 100 | 필드의 부적절한 값 |
