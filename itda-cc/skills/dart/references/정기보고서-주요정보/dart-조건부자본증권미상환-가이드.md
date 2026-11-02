# 조건부 자본증권 미상환 잔액 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2020008
추출일: 2026-04-28

## 기본 정보

| 메서드 | 요청URL | 인코딩 | 출력포멧 |
|--------|--------|--------|---------|
| GET | https://opendart.fss.or.kr/api/cndlCaplScritsNrdmpBlce.json | UTF-8 | JSON |
| GET | https://opendart.fss.or.kr/api/cndlCaplScritsNrdmpBlce.xml | UTF-8 | XML |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수여부 | 값설명 |
|--------|------|------|---------|--------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 고유번호(8자리) |
| bsns_year | 사업연도 | STRING(4) | Y | 사업연도(4자리) ※ 2015년 이후 정보제공 |
| reprt_code | 보고서 코드 | STRING(5) | Y | 1분기: 11013, 반기: 11012, 3분기: 11014, 사업: 11011 |

## 응답 결과

| 응답키 | 명칭 | 출력설명 |
|--------|------|---------|
| result.status | 에러 및 정보 코드 | 메시지 설명 참조 |
| result.message | 에러 및 정보 메시지 | 메시지 설명 참조 |
| list.rcept_no | 접수번호 | 접수번호(14자리) |
| list.corp_cls | 법인구분 | Y(유가), K(코스닥), N(코넥스), E(기타) |
| list.corp_code | 고유번호 | 고유번호(8자리) |
| list.corp_name | 회사명 | 공시대상회사명 |
| list.yy1_below | 1년 이하 | 1년 이하 |
| list.yy1_excess_yy2_below | 1년초과 2년이하 | 1년초과 2년이하 |
| list.yy2_excess_yy3_below | 2년초과 3년이하 | 2년초과 3년이하 |
| list.yy3_excess_yy4_below | 3년초과 4년이하 | 3년초과 4년이하 |
| list.yy4_excess_yy5_below | 4년초과 5년이하 | 4년초과 5년이하 |
| list.yy5_excess_yy10_below | 5년초과 10년이하 | 5년초과 10년이하 |
| list.yy10_excess_yy20_below | 10년초과 20년이하 | 10년초과 20년이하 |
| list.yy20_excess_yy30_below | 20년초과 30년이하 | 20년초과 30년이하 |
| list.yy30_excess | 30년초과 | 30년초과 |
| list.sm | 합계 | 합계 |
| list.stlm_dt | 결산기준일 | YYYY-MM-DD |

## 에러 코드

| 코드 | 설명 |
|------|------|
| 000 | 정상 |
| 010 | 등록되지 않은 키 |
| 013 | 조회된 데이타가 없습니다 |
| 020 | 요청 제한 초과(20,000건 이상) |
| 100 | 필드의 부적절한 값 |
| 800 | 시스템 점검으로 서비스 중지 |
| 900 | 정의되지 않은 오류 |
