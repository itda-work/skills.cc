# 채무증권 발행실적 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2020003
추출일: 2026-04-28

## 기본 정보

| 메서드 | 요청URL | 인코딩 | 출력포멧 |
|--------|--------|--------|---------|
| GET | https://opendart.fss.or.kr/api/detScritsIsuAcmslt.json | UTF-8 | JSON |
| GET | https://opendart.fss.or.kr/api/detScritsIsuAcmslt.xml | UTF-8 | XML |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수여부 | 값설명 |
|--------|------|------|---------|--------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 고유번호(8자리) |
| bsns_year | 사업연도 | STRING(4) | Y | 사업연도(4자리) ※ 2015년 이후 정보제공 |
| reprt_code | 보고서 코드 | STRING(5) | Y | 11013(1분기), 11012(반기), 11014(3분기), 11011(사업) |

## 응답 결과

| 응답키 | 명칭 | 출력설명 |
|--------|------|---------|
| result.status | 에러 및 정보 코드 | 메시지 설명 참조 |
| result.message | 에러 및 정보 메시지 | 메시지 설명 참조 |
| list.rcept_no | 접수번호 | 접수번호(14자리) |
| list.corp_cls | 법인구분 | Y(유가), K(코스닥), N(코넥스), E(기타) |
| list.corp_code | 고유번호 | 고유번호(8자리) |
| list.corp_name | 공시대상회사명 | 공시대상회사명 |
| list.isu_cmpny | 발행회사 | 발행회사 |
| list.scrits_knd_nm | 증권종류 | 증권종류 |
| list.isu_mth_nm | 발행방법 | 발행방법 |
| list.isu_de | 발행일자 | YYYYMMDD |
| list.facvalu_totamt | 권면(전자등록)총액 | 권면총액 |
| list.intrt | 이자율 | 이자율 |
| list.evl_grad_instt | 평가등급(평가기관) | 평가등급 |
| list.mtd | 만기일 | YYYYMMDD |
| list.repy_at | 상환여부 | 상환여부 |
| list.mngt_cmpny | 주관회사 | 주관회사 |
| list.stlm_dt | 결산기준일 | YYYY-MM-DD |

## 에러 코드

| 코드 | 설명 |
|------|------|
| 000 | 정상 |
| 010 | 등록되지 않은 키 |
| 011 | 일시적으로 사용 중지된 키 |
| 012 | 접근할 수 없는 IP |
| 013 | 조회된 데이터 없음 |
| 020 | 요청 제한 초과 (20,000건 이상) |
| 100 | 필드의 부적절한 값 |
| 800 | 시스템 점검 중 |
| 900 | 정의되지 않은 오류 |
| 901 | 개인정보 보유기간 만료 |
