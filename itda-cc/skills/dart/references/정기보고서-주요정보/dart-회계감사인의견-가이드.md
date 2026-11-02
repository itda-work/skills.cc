# 회계감사인의 명칭 및 감사의견 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2020009
추출일: 2026-04-28

## 기본 정보

| 항목 | 내용 |
|------|------|
| 메서드 | GET |
| 요청URL (JSON) | https://opendart.fss.or.kr/api/accnutAdtorNmNdAdtOpinion.json |
| 요청URL (XML) | https://opendart.fss.or.kr/api/accnutAdtorNmNdAdtOpinion.xml |
| 인코딩 | UTF-8 |
| 출력포멧 | JSON / XML |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수여부 | 값설명 |
|--------|------|------|---------|--------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 고유번호(8자리) |
| bsns_year | 사업연도 | STRING(4) | Y | 사업연도(4자리) ※ 2015년 이후 부터 정보제공 |
| reprt_code | 보고서 코드 | STRING(5) | Y | 11013(1분기), 11012(반기), 11014(3분기), 11011(사업보고서) |

## 응답 결과

| 응답키 | 명칭 | 출력설명 |
|--------|------|---------|
| rcept_no | 접수번호 | 접수번호(14자리) |
| corp_cls | 법인구분 | Y(유가), K(코스닥), N(코넥스), E(기타) |
| corp_code | 고유번호 | 공시대상회사의 고유번호(8자리) |
| corp_name | 회사명 | 공시대상회사명 |
| bsns_year | 사업연도 | 당기/전기/전전기 |
| adtor | 감사인 | 감사인명 |
| adt_opinion | 감사의견 | 감사의견 |
| core_adt_matter | 핵심감사사항 | 2019.12.9. 추가 |

## 에러 코드

| 코드 | 메시지 |
|------|--------|
| 000 | 정상 |
| 010 | 등록되지 않은 키 |
| 013 | 조회된 데이타가 없음 |
| 020 | 요청 제한 초과(20,000건 이상) |
| 100 | 필드의 부적절한 값 |
| 800 | 시스템 점검 중 |
| 900 | 정의되지 않은 오류 |
