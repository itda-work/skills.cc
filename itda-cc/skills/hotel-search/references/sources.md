# 데이터 소스 — Xotelo API (트립어드바이저 메타서치)

가격 소스는 **Xotelo**(https://xotelo.com/) 무료 API 하나다. itda-cc 판은 스크립트가 직접 요청한다
(`itda-cc/shared/cc_http.py` — UA `Mozilla/5.0`, 브라우저·API 키 불필요). 아래 사실은 **라이브 실측으로 확정**했다(#1013, 2026-07-09 —
추측 금지·실측 우선(`skill-web-probe-aside`), data-accuracy: plausible ≠ correct).

## 엔드포인트 (무료 `data.xotelo.com` — 실측)

| endpoint | 파라미터 | 무료 | 반환 |
|---|---|:---:|---|
| `/rates` | `hotel_key,chk_in,chk_out,currency[,adults,rooms]` | ✅ | OTA별 `{code,name,rate,tax}` |
| `/heatmap` | `hotel_key,chk_out` | ✅ | 싼날/평균/비싼날 달력 |
| `/list` | `location_key[,offset,limit,sort]` | ❌ | 유효 geo(g60763)로도 400 — 무료 티어 폐기, 미사용 |
| `/search` | `query` | ❌ | 401 "RapidAPI 전용"(유료 키) — 미사용 |

- **인증 없음** — `/rates`·`/heatmap` 은 키 없이 200. 헤더 없이(범용 UA `Mozilla/5.0`) 성립한다(2026-10-01 실측). robots.txt 는 404(Next.js 404 페이지 — 규칙 없음).
- **응답이 조회 조건을 되비친다** — `/rates` 는 `chk_in`·`chk_out`·`currency`, `/heatmap` 은 `chk_out`. 판독이 요청과 대조한다(`mismatch`).
  `hotel_key`·`adults`·`rooms` 는 되비치지 않는다. 응답 `timestamp`(epoch ms)를 조회 시각(KST)으로 표에 싣는다.
- **`rate` = 1박 평균가** — 실측: 1박 \$308 / 2박 \$261 / 3박 \$243 (박수↑ 시 1박 단가↓). 각 OTA에서
  **예약 가능한 최저 객실**의 1박가 대표값. 총액 = `rate × nights`. **객실 타입 구분·객실별 가격 없음**.
- **`tax` 대부분 null** — 세금 분해 미제공.
- **OTA 노출 개수 편차** — 호텔·날짜별 1~4개. 실측: 노보텔 서울(4개: Klook·Trip.com·Agoda·Booking) vs
  써미트 서울 특정일(Trip.com 1개).

### 요금 응답 예 (`/rates`)

```json
{"error": null,
 "result": {"chk_in": "2026-08-15", "chk_out": "2026-08-17", "currency": "USD",
            "rates": [{"code": "BookingCom", "name": "Booking.com", "rate": 290, "tax": null},
                      {"code": "Agoda", "name": "Agoda.com", "rate": 289, "tax": null}]}}
```

파서: `xotelo.parse_rates` → 공통 offer(`ota_code,ota_name,per_night,total,tax,per_night_krw,total_krw`),
1박가 오름차순. 실측 fixture: `tests/fixtures/xotelo_rates_multi.json`·`xotelo_heatmap.json`·
`xotelo_rates_error_currency.json`(2026-07-09)·`live_rates_20261119.json`·`live_heatmap_20261121.json`·`erapi_usd_20261001.json`(2026-10-01),
테스트 `tests/test_xotelo.py`·`tests/test_fx.py`.

## hotel_key / location_key (TripAdvisor 식별자)

- **hotel_key** = `g<geo>-d<hotel>` (예 `g294197-d5250436`). TripAdvisor 호텔 페이지 URL
  `Hotel_Review-g294197-d5250436-Reviews-…html` 에서 추출(`xotelo.extract_hotel_key`, URL·순수키 공용).
- 무료 이름 검색이 없으므로 hotel_key 는 **에이전트 web_search** 또는 **사용자 URL 직접 제공**으로
  확보한다(SKILL.md). 서울 geo = `g294197`(실측 커버리지 확인).

## 통화 · 환율

- Xotelo 허용 통화(실측): **USD·GBP·EUR·CAD·CHF·AUD·JPY·CNY·INR·THB·BRL·HKD·RUB·BZD** — **KRW 없음**.
- → USD 등으로 수집 후 `open.er-api.com/v6/latest/<base>`(무료·키 없음, `.rates.KRW`)로 원화 환산 표시
  (`fx.krw_rate`). 판독 실패는 조용히 덮지 않고 출력에 명시(no-silent-fallback).
- **이용 조건**(https://www.exchangerate-api.com/docs/free — 2026-10-01 판독): 키 없는 Open API 는 **출처 표기 필수**
  ("Rates By Exchange Rate API" 링크) → 출력 주석에 늘 싣는다. 하루 한 번 갱신·캐시 허용·한 시간에 한 번 넘게 부르지
  말라는 권고 → 캐시 폴더(기본 `~/.cache/itda-cc/hotel-search/`)에 받은 날을 넣은 이름(`fx-<통화>-<YYYYMMDD KST>.json`)으로 저장해 하루 한 번만 받는다.
  재배포 불가 → 환율 표를 내보내지 않고 환산에만 쓴다. `time_last_update_unix` 가 48시간 넘게 묵으면 경고한다.
- robots.txt 는 404(nginx — 규칙 없음, 2026-10-01).

## 정확성 게이트 (P3 — 통과 2026-07-09, #1013)

구 스킬(0.1.0)은 **TripAdvisor 메타 가격을 "불안정"이라며 배제**했었다(그때 소스는 Booking/Agoda DOM).
Xotelo 는 그 메타값을 API 로 노출하므로, 채택 전 **Xotelo `/rates` 값 vs 실제 Booking.com 값을 라이브
1회 교차검증**했다(노보텔 앰배서더 서울 동대문 `g294197-d14159727`, 2026-08-13 체크인):

| 숙박 | 실제 Booking.com 1박 환산 | Xotelo Booking.com 1박 | 델타 |
|---|---|---|---|
| 1박 | \$212.69 | \$213 | +0.15% |
| 2박 | \$234.02 | \$234 | −0.01% |
| 3박 | \$260.67 | \$261 | +0.13% |

→ 세 숙박일수 전부 **오차 0.2% 이내**(반올림 수준). Xotelo 가 실제 OTA 표시가를 재현함을 확인 →
채택 확정. 레거시 자산(`booking.py`·`agoda.py`·`booking-live-probe.md`·`output.offers_to_markdown`·
해당 파서 테스트)은 삭제 완료.

> 단, n=1 호텔·1 date-cluster 검증이다. 메타값은 원칙적으로 실제 예약가와 다를 수 있으므로(data-accuracy)
> SKILL.md 는 "실제 예약가와 다를 수 있음" 캐비엇을 상시 노출한다.
