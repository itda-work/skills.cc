# 해외 증권시장 주권등 상장폐지 결정 API 개발가이드

출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020030
추출일: 2026-04-28

## 기본 정보

| 항목 | 내용 |
|------|------|
| 메서드 | GET |
| 요청URL (JSON) | https://opendart.fss.or.kr/api/ovDlstDecsn.json |
| 요청URL (XML) | https://opendart.fss.or.kr/api/ovDlstDecsn.xml |
| 인코딩 | UTF-8 |

## 요청 인자

| 요청키 | 명칭 | 타입 | 필수 | 설명 |
|--------|------|------|------|------|
| crtfc_key | API 인증키 | STRING(40) | Y | 발급받은 40자리 인증키 |
| corp_code | 고유번호 | STRING(8) | Y | 8자리 고유번호 |
| bgn_de | 시작일 | STRING(8) | Y | 검색시작 접수일자(YYYYMMDD); 2015년 이후 |
| end_de | 종료일 | STRING(8) | Y | 검색종료 접수일자(YYYYMMDD); 2015년 이후 |

## 응답 결과

| 응답키 | 명칭 | 설명 |
|--------|------|------|
| rcept_no | 접수번호 | 14자리 |
| corp_cls | 법인구분 | Y(유가), K(코스닥), N(코넥스), E(기타) |
| corp_code | 고유번호 | 8자리 |
| corp_name | 회사명 | 공시대상회사명 |
| dlststk_ostk_cnt | 상장폐지 보통주식 수 | 주식 수 |
| dlststk_estk_cnt | 상장폐지 기타주식 수 | 주식 수 |
| lstex_nt | 상장거래소(소재국가) | 거래소/국가 |
| dlst_rs | 상장폐지사유 | 상장폐지사유 |

## 에러 코드

| 코드 | 메시지 |
|------|--------|
| 000 | 정상 |
| 010 | 등록되지 않은 키 |
| 013 | 조회된 데이타가 없습니다 |
| 020 | 요청 제한 초과 |
| 100 | 부적절한 필드값 |
| 901 | 사용자 계정의 개인정보 보유기간 만료 |
