# 사외이사 및 그 변동현황 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2020012
추출일: 2026-04-28

## 기본 정보

| 항목 | 내용 |
|------|------|
| 메서드 | GET |
| 요청URL (JSON) | https://opendart.fss.or.kr/api/outcmpnyDrctrNdChangeSttus.json |
| 요청URL (XML) | https://opendart.fss.or.kr/api/outcmpnyDrctrNdChangeSttus.xml |
| 인코딩 | UTF-8 |
| 출력포멧 | JSON, XML |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수여부 | 값설명 |
|--------|------|------|---------|--------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 인증키(40자리) |
| corp_code | 고유번호 | STRING(8) | Y | 공시대상회사의 고유번호(8자리) |
| bsns_year | 사업연도 | STRING(4) | Y | 사업연도(2015년 이후) |
| reprt_code | 보고서 코드 | STRING(5) | Y | 11013(1분기), 11012(반기), 11014(3분기), 11011(사업보고서) |

## 응답 결과

| 응답키 | 명칭 | 설명 |
|--------|------|------|
| rcept_no | 접수번호 | 14자리 접수번호 |
| corp_cls | 법인구분 | Y(유가), K(코스닥), N(코넥스), E(기타) |
| corp_code | 고유번호 | 8자리 고유번호 |
| corp_name | 회사명 | 공시대상회사명 |
| drctr_co | 이사의 수 | 전체 이사 수 |
| otcmp_drctr_co | 사외이사 수 | 사외이사 수 |
| apnt | 선임 | 사외이사 변동현황(선임) |
| rlsofc | 해임 | 사외이사 변동현황(해임) |
| mdstrm_resig | 중도퇴임 | 사외이사 변동현황(중도퇴임) |
| stlm_dt | 결산기준일 | YYYY-MM-DD |

## 에러 코드

| 코드 | 메시지 |
|------|--------|
| 000 | 정상 |
| 010 | 등록되지 않은 키 |
| 013 | 조회된 데이터 없음 |
| 020 | 요청 제한 초과(20,000건 이상) |
| 021 | 조회 가능 회사 개수 초과(최대 100건) |
| 100 | 필드의 부적절한 값 |
| 900 | 정의되지 않은 오류 |
