# 상각형 조건부자본증권 발행결정 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020037
추출일: 2026-04-28

## 기본 정보

| 항목 | 내용 |
|------|------|
| 메서드 | GET |
| JSON URL | https://opendart.fss.or.kr/api/wdCocobdIsDecsn.json |
| XML URL | https://opendart.fss.or.kr/api/wdCocobdIsDecsn.xml |
| 인코딩 | UTF-8 |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수 | 설명 |
|--------|------|------|------|------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 고유번호(8자리) |
| bgn_de | 시작일 | STRING(8) | Y | 검색시작 접수일자(YYYYMMDD) ※ 2015년 이후 |
| end_de | 종료일 | STRING(8) | Y | 검색종료 접수일자(YYYYMMDD) ※ 2015년 이후 |

## 응답 결과

| 응답키 | 명칭 | 설명 |
|--------|------|------|
| rcept_no | 접수번호 | 14자리 |
| corp_cls | 법인구분 | Y(유가), K(코스닥), N(코넥스), E(기타) |
| corp_name | 회사명 | 공시대상회사명 |
| bd_fta | 사채 총액 | 권면(전자등록)총액 (원) |
| bd_mtd | 사채만기일 | 만기일자 |

## 에러 코드

| 코드 | 메시지 |
|------|--------|
| 000 | 정상 |
| 010 | 등록되지 않은 키 |
| 013 | 조회된 데이타가 없습니다 |
| 020 | 요청 제한 초과(20,000건 이상) |
| 021 | 조회 가능한 회사 개수 초과(최대 100건) |
| 100 | 필드의 부적절한 값 |
