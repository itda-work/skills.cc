# 이사·감사 전체의 보수현황(주주총회 승인금액) API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2020014
추출일: 2026-04-28

## 기본 정보

| 항목 | 내용 |
|------|------|
| 메서드 | GET |
| 요청URL | https://opendart.fss.or.kr/api/drctrAdtAllMendngSttusGmtsckConfmAmount.json |
| 인코딩 | UTF-8 |
| 출력포멧 | JSON / XML |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수 | 값설명 |
|--------|------|------|------|--------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 고유번호(8자리) |
| bsns_year | 사업연도 | STRING(4) | Y | 사업연도(4자리) ※ 2015년 이후 정보제공 |
| reprt_code | 보고서 코드 | STRING(5) | Y | 11013(1분기) / 11012(반기) / 11014(3분기) / 11011(사업보고서) |

## 응답 결과

| 응답키 | 명칭 | 출력설명 |
|--------|------|---------|
| result.status | 에러 및 정보 코드 | 메시지 설명 참조 |
| list.rcept_no | 접수번호 | 접수번호(14자리) |
| list.corp_cls | 법인구분 | Y(유가) / K(코스닥) / N(코넥스) / E(기타) |
| list.corp_name | 회사명 | 공시대상회사명 |
| list.nmpr | 인원수 | 인원수 |
| list.gmtsck_confm_amount | 주주총회 승인금액 | 승인금액 |

## 에러 코드

| 코드 | 설명 |
|------|------|
| 000 | 정상 |
| 010 | 등록되지 않은 키입니다 |
| 013 | 조회된 데이타가 없습니다 |
| 100 | 필드의 부적절한 값입니다 |
| 800 | 시스템 점검으로 인한 서비스 중지 |
