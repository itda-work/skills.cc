# 타법인 출자현황 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2019015
추출일: 2026-04-28

## 기본 정보

| 항목 | 설명 |
|------|------|
| 메서드 | GET |
| 요청URL (JSON) | https://opendart.fss.or.kr/api/otrCprInvstmntSttus.json |
| 요청URL (XML) | https://opendart.fss.or.kr/api/otrCprInvstmntSttus.xml |
| 인코딩 | UTF-8 |
| 출력포멧 | JSON, XML |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수여부 | 값설명 |
|--------|------|------|---------|---------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 고유번호(8자리) |
| bsns_year | 사업연도 | STRING(4) | Y | 사업연도(4자리), 2015년 이후 |
| reprt_code | 보고서 코드 | STRING(5) | Y | 11013(1분기), 11012(반기), 11014(3분기), 11011(사업보고서) |

## 응답 결과

| 응답키 | 명칭 | 출력설명 |
|--------|------|---------|
| result.status | 에러 및 정보 코드 | 메시지 설명 참조 |
| result.message | 에러 및 정보 메시지 | 메시지 설명 참조 |
| list.rcept_no | 접수번호 | 접수번호(14자리) |
| list.corp_cls | 법인구분 | Y(유가), K(코스닥), N(코넥스), E(기타) |
| list.corp_code | 고유번호 | 고유번호(8자리) |
| list.corp_name | 공시대상회사명 | 공시대상회사명 |
| list.inv_prm | 법인명 | 법인명 |
| list.frst_acqs_de | 최초취득일자 | YYYYMMDD |
| list.invstmnt_purps | 출자목적 | 출자목적 |
| list.frst_acqs_amount | 최초취득금액 | 최초취득금액 |
| list.bsis_blce_qy | 기초잔액수량 | 기초잔액수량 |
| list.trmend_blce_qy | 기말잔액수량 | 기말잔액수량 |
| list.stlm_dt | 결산기준일 | YYYY-MM-DD |

## 에러 코드

| 코드 | 의미 |
|------|------|
| 000 | 정상 |
| 010 | 등록되지 않은 키 |
| 013 | 조회된 데이터 없음 |
| 020 | 요청 제한 초과 |
| 100 | 필드 부적절한 값 |
| 800 | 시스템 점검 중 |
| 900 | 정의되지 않은 오류 |
