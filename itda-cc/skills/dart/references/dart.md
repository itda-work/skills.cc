# DART 전자공시시스템 — collect_company.py 상세

경쟁사 분석에 필요한 기업 공시 데이터를 수집합니다.

## API 키

`.env` 에 `DART_API_KEY=<40자리 키>` 로 적는다(https://opendart.fss.or.kr 회원가입 → 인증키 즉시 발급).
스크립트가 `--env-file` → `./.env` → `~/.env` 가운데 처음 찾은 파일 하나에서 읽고, 요청의 `crtfc_key` 에 넣는다.
키 값은 출력·오류·로그에 싣지 않는다(요청 URL 은 가려서 싣는다).

> **주의**: 인증키 복사 시 앞뒤 공백이나 줄바꿈이 포함되지 않도록 하세요.

## 서브커맨드

| 커맨드 | 역할 | 받는 응답 |
|-------|------|-----------|
| `search` | 회사명으로 고유번호 검색 | corpCode ZIP |
| `info` | 기업개황 | company.json |
| `finance` | 재무제표 주요계정(`--detail` 전체) | fnlttSinglAcnt(All).json (+연도 없으면 list.json) |
| `employees` | 직원현황 | empSttus.json |
| `profile` | 종합 (위 3개 한번에) | corpCode ZIP → company·fnlttSinglAcnt·empSttus |
| `disclosure` | 공시 목록(기간 전량) | list.json 쪽마다 |
| `business` | 사업보고서 원문 | document ZIP (+접수번호 없으면 list.json) |
| `compare` | 다기업 재무 비교 | fnlttMultiAcnt.json (+이름이면 corpCode ZIP) |
| `raw` | 전용 명령이 없는 엔드포인트 | `<엔드포인트>.json` |

명령 한 번에 결과가 나온다. 옵션 전체는 SKILL.md 가 정본이다.

## 출력 예시 (profile)

```json
{
  "status": "ok",
  "corp_code": "00126380",
  "corp_name": "삼성전자",
  "stock_code": "005930",
  "year": "2024",
  "company_info": {
    "ceo_nm": "한종희",
    "induty_code": "264",
    "est_dt": "19690113",
    "adres": "경기도 수원시 영통구 삼성로 129"
  },
  "financials": [
    {"account_nm": "매출액", "thstrm_amount": "258935488000000", "frmtrm_amount": "..."},
    {"account_nm": "영업이익(손실)", "thstrm_amount": "6567200000000", "frmtrm_amount": "..."}
  ],
  "employees": [
    {"fo_bbm": "DS부문", "sm": "51000", "avrg_cnwk_sdytrn": "12.5"}
  ]
}
```

## raw 호출 — 엔드포인트 disambiguation

`collect_company.py raw --endpoint <이름> --param k=v ...`로 미구현 엔드포인트를 직접 호출할 때,
이름이 비슷해 헷갈리는 것들 (모두 우리 `references/` 분류 가이드에 정본 명세 존재):

| 엔드포인트 | 한글명 | 비고 |
|-----------|--------|------|
| `fnlttSinglAcnt` | 단일회사 주요계정 | 약 30항목 (`finance` 기본) |
| `fnlttSinglAcntAll` | 단일회사 전체 재무제표 | 약 176항목 (`finance --detail`) |
| `pifricDecsn` | 유무상증자 결정 | 유상+무상 동시 |
| `piicDecsn` | 유상증자 결정 | 유상만 |
| `fricDecsn` | 무상증자 결정 | 무상만 |
| `irdsSttus` | 증자(감자) 현황 | 정기보고서 |
| `alotMatter` | 배당에 관한 사항 | 정기보고서 |
| `tesstkAcqsDspsSttus` | 자기주식 취득·처분 현황 | 정기보고서 |
| `accnutAdtorNmNdAdtOpinion` | 회계감사인 명칭·감사의견 | 정기보고서 |
| `lwstLg` | 소송 등의 제기 | 주요사항, `bgn_de`·`end_de` 필요 |
| `cvbdIsDecsn` | 전환사채권 발행결정 | 주요사항, 기간 필요 |
| `exbdIsDecsn` | 교환사채권 발행결정 | 주요사항, 기간 필요 |

> 정기보고서 계열은 `corp_code`·`bsns_year`·`reprt_code`(11011 사업 / 11012 반기 / 11013 1분기 / 11014 3분기),
> 주요사항 결정 계열은 `corp_code`·`bgn_de`·`end_de`(YYYYMMDD)를 요구합니다.
> 전체 80여 개 엔드포인트 명세는 상위 `references/` 6개 분류 가이드를 참고하세요.

## corpCode.xml — 캐시

`search`·`profile`·`compare --names` 는 DART 전체 기업 목록(corpCode.xml, ZIP 약 3.6MB → XML 약 30MB, 2026-09-30 실측)을 쓴다.
스크립트가 `~/.cache/itda-skills/itda-cc/dart/corpcode-<날짜>.zip` 에 캐시하고 7일 안에 받은 것이 있으면 다시 받지 않는다
(`--cache-dir` 로 바꾸고 `--refresh` 로 새로 받는다). 오류 응답은 캐시하지 않는다.

## 에러 코드

| 코드 | 의미 | 조치 |
|------|------|------|
| 000 | 정상 | - |
| 010 | 등록되지 않은 키 | `.env` 의 `DART_API_KEY` 확인 — 고친 뒤 같은 명령을 다시 실행 |
| 013 | 데이터 없음 | 연도/보고서 유형 변경 |
| 020 | 요청 제한 초과 | 스크립트가 같은 명령 안에서 2초·5초 쉬고 다시 받는다(최대 3번) |
| 800 · 900 | 시스템 점검 · 정의되지 않은 오류 | 020 과 같이 다시 받는다(3번째도 같으면 멈춘다) |
