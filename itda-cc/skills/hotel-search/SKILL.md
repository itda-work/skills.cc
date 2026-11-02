---
name: hotel-search
description: >
  같은 호텔의 예약 사이트별(Booking·Agoda·Trip.com·공식사이트) 실시간 요금을 Claude Code 에서 한 번에 비교해 최저가와 예약 링크를 찾습니다.
  "신라호텔 서울 8월 1일부터 2박 최저가 비교해줘", "부킹이랑 아고다 중 어디가 싸?", "이번 주말 싼 날짜 알려줘"처럼 말하면 됩니다. 키 불필요.
  [책임 경계] 본 스킬은 Claude Code 직접 조회 전담 — itda-travel:hotel-search 는 Cowork·itda-hyve 경로.
license: Apache-2.0
compatibility: "Claude Code 전용. Python 3.10+(표준 라이브러리만). 스크립트가 data.xotelo.com(요금·달력)과 open.er-api.com(환율)에 직접 요청한다. 키·계정 불필요."
allowed-tools: "Bash, Read, Write, WebSearch"
user-invocable: true
argument-hint: "호텔명(또는 TripAdvisor URL) + 체크인·체크아웃 날짜 — 예: 신라호텔 서울 8월 1일부터 2박"
metadata:
  author: "스킬.잇다 <dev@itda.work>"
  category: "data-fetching"
  status: "experimental"
  version: "0.1.0"
  created_at: "2026-11-02"
  updated_at: "2026-11-02"
  tags: "hotel, price, comparison, travel, tripadvisor, xotelo, ota, booking, agoda, read-only, api"
---

# hotel-search

같은 호텔인데 Booking·Agoda·Trip.com마다 값이 다르다. 탭 여러 개를 띄워 날짜를 똑같이 넣고 비교하는 노동을 없애려고,
호텔 하나 + 날짜로 **여러 예약 사이트의 1박가·총액을 한 표**로 모으고 **싼 날/비싼 날 달력**도 보여 줍니다.
**조회 전용** — 예약·결제는 하지 않습니다.

- 가격 소스는 **Xotelo** 무료 API(트립어드바이저 메타서치 — 여러 예약 사이트의 실시간 요금을 한 번에 돌려준다).
- **명령 한 번에 결과가 나온다** — 스크립트가 Xotelo 와 환율 API 에 직접 요청한다. 키·계정·`.env` 가 필요 없다.

| 서브커맨드 | 하는 일 | 요청 |
|---|---|---|
| `resolve <URL\|텍스트>` | TripAdvisor URL/문자열에서 `hotel_key`(`g<geo>-d<hotel>`) 추출 | 없음 |
| `rates` | 예약 사이트별 1박가·총액 비교표(원화 환산 병기) | Xotelo 1회 + 환율(하루 한 번) |
| `heatmap` | 싼 날/평균/비싼 날 가격 달력 | Xotelo 1회 |

## hotel_key 를 먼저 확보한다 (이름→키)

Xotelo 무료 티어에는 이름 검색이 없다(`/search`=유료, `/list`=고장, 실측 #1013). 조회 전에 `hotel_key` 를 **두 경로 중 하나로** 얻는다.

1. **WebSearch** — 사용자가 호텔명만 줄 때. `"<호텔명> tripadvisor hotel"` 로 검색해 `tripadvisor.com/Hotel_Review-g…-d….html` URL 을
   찾고 `resolve` 로 키를 뽑는다. 검색 결과가 맞는 호텔인지 **이름·도시로 확인**한다(동명 호텔 주의).
   TripAdvisor 페이지는 열지 않는다 — URL 문자열에서 키만 뽑는다.
2. **사용자가 URL/키를 직접 줄 때** — 그대로 `--url`/`--hotel-key`.

## 실행

**먼저** 스킬을 불러올 때 받은 base directory(이 SKILL.md 가 있는 절대경로)를 `SKILL_DIR` 에 넣고 아래 블록을 실행한다 — 블록은 그 값을 검증해 쓰고, 넣지 못했을 때만 설치 위치를 찾는다(후보가 여럿이면 멈춘다).

```bash
# SKILL_DIR 확정(skill-dir-resolution) — 스킬을 불러올 때 받은 base directory 를 먼저 SKILL_DIR="그 경로" 로 넣는다(항상)
# 블록은 그 값을 검증해 쓰고, 넣지 못했을 때만 설치 위치를 찾는다 — SKILL.md 가 있는 후보가 하나일 때만 받고 아니면 멈춘다
SKILL_DIR=$(sh -c '
S=$1 P=$2 H=${5:-$HOME/.claude}
ok() { d=${1%/}; [ "${d##*/}" = "$S" ] && [ -f "$d/SKILL.md" ] && (cd "$d" && pwd -P); }
[ -n "$3" ] && { ok "$3" && exit; d=${3%/}; [ "${d##*/}" = "$S" ] && echo "SKILL_DIR 무시: $3 에 SKILL.md 가 없다" >&2; }
[ -n "$4" ] && { ok "$4/skills/$S" && exit; echo "CLAUDE_PLUGIN_ROOT 무시: $4/skills/$S 에 SKILL.md 가 없다" >&2; }
c=$(for d in "$H"/plugins/synced/*/"$P"/skills/"$S" "$H"/plugins/synced/*/"$P"~*/skills/"$S" "$H"/plugins/cache/*/"$P"/*/skills/"$S" \
    /root/.claude/plugins/synced/*/"$P"/skills/"$S" /root/.claude/plugins/synced/*/"$P"~*/skills/"$S" \
    /sessions/*/mnt/.remote-plugins/*/skills/"$S" /sessions/*/mnt/.claude/skills/"$S"; do ok "$d"; done | sort -u)
[ "$(printf "%s\n" "$c" | grep -c .)" -gt 1 ] && { printf "SKILL_DIR 후보가 여럿이다 — 어느 설치본이 쓰이는지 모른다:\n%s\n" "$c" >&2; exit 1; }
printf "%s\n" "$c"' _ hotel-search itda-cc "${SKILL_DIR:-}" "${CLAUDE_PLUGIN_ROOT:-}" "${CLAUDE_CONFIG_DIR:-}")
: "${SKILL_DIR:?정하지 못했다 — 스킬을 불러올 때 받은 base directory(이 SKILL.md 가 있는 절대경로)를 SKILL_DIR 에 넣고 이 블록을 다시 실행하라}"
```

```powershell
# SKILL_DIR 확정(skill-dir-resolution) — bash 블록과 같은 계약. 스킬을 불러올 때 받은 base directory 를 먼저 $env:SKILL_DIR 에 넣는다(항상)
$S = 'hotel-search'; $P = 'itda-cc'; $H = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $HOME '.claude' }
$ok = { param($d) if ($d -and (Split-Path $d.TrimEnd('\', '/') -Leaf) -eq $S -and (Test-Path -LiteralPath (Join-Path $d 'SKILL.md'))) { (Resolve-Path -LiteralPath $d).Path.TrimEnd('\', '/') } }
$c = @(& $ok $env:SKILL_DIR) + @(if ($env:CLAUDE_PLUGIN_ROOT) { & $ok (Join-Path (Join-Path $env:CLAUDE_PLUGIN_ROOT 'skills') $S) })
if (-not $c) { $c = @(@(Get-Item -Path (Join-Path $H "plugins/synced/*/*/skills/$S") -ErrorAction SilentlyContinue | Where-Object { $_.Parent.Parent.Name -eq $P -or $_.Parent.Parent.Name -like "$P~*" }) + @(Get-Item -Path (Join-Path $H "plugins/cache/*/$P/*/skills/$S") -ErrorAction SilentlyContinue) | Where-Object { $_.PSIsContainer } | ForEach-Object { & $ok $_.FullName } | Sort-Object -Unique) }
if ($c.Count -gt 1) { Write-Warning "SKILL_DIR 후보가 여럿이다 — 어느 설치본이 쓰이는지 모른다: $($c -join ', ')"; $c = @() }
if (-not $c) { throw 'SKILL_DIR 을 정하지 못했다 — 스킬을 불러올 때 받은 base directory(이 SKILL.md 가 있는 절대경로)를 $env:SKILL_DIR 에 넣고 이 블록을 다시 실행하라' }
$env:SKILL_DIR = $c[0]
```

```bash
# macOS/Linux
python3 "$SKILL_DIR/scripts/hotel_search.py" resolve "https://www.tripadvisor.com/Hotel_Review-g294197-d5250436-Reviews-Summit_Hotel_Seoul-Seoul.html"
# → g294197-d5250436

python3 "$SKILL_DIR/scripts/hotel_search.py" rates --hotel-key g294197-d14159727 \
  --checkin 2026-11-19 --checkout 2026-11-21 --name "노보텔 앰배서더 서울 동대문"

python3 "$SKILL_DIR/scripts/hotel_search.py" heatmap --hotel-key g294197-d14159727 --checkout 2026-11-21
```

```powershell
# Windows
py -3 "$env:SKILL_DIR\scripts\hotel_search.py" rates --url "<TripAdvisor URL>" --checkin 2026-11-19 --checkout 2026-11-21 --name "<호텔명>"
```

### 요금 비교 (rates)

- `rate` 는 각 예약 사이트에서 **예약 가능한 최저 객실의 1박 평균가**다. 총액 = 1박가 × 박수. 1박가 오름차순(최저가에 🏆).
- 표 머리에 **조회 시각**(Xotelo 응답 시각, KST)이 찍힌다 — 그대로 보여 준다. 같은 질문을 다시 받으면 명령을 다시 실행한다(요금은 캐시하지 않는다).
- Xotelo 는 KRW 미지원이라 **USD 등으로 받아 원화로 환산**해 `"519,814원 (USD 384)"` 처럼 병기한다(참고값 — 예약가 아님). `--no-krw` 로 끈다.
  환율은 하루 한 번 갱신되므로 `~/.cache/itda-cc/hotel-search/` 에 날짜별로 저장해 **하루 한 번만** 받는다(이용 조건 — 캐시 권장).
- 환율 출처 표기("Rates By Exchange Rate API")는 이용 조건이라 출력에 늘 붙는다 — 빼지 않고 함께 보여 준다.
- `warnings`(원화 환산 생략 사유·묵은 환율·버린 행)는 **전부 그대로** 사용자에게 전한다.

**예약 링크** — `--name`(호텔명)을 주면 각 사이트 셀이 링크가 된다(라이브 검증 #1015):
- **Booking.com** = 그 호텔·그 날짜·인원이 채워진 검색 링크(바로 랜딩).
- **Agoda·Trip.com·Klook·공식사이트 등** = Google 검색 링크(`<호텔명> <사이트>`) — 이들은 내부 ID 가 있어야 해 호텔명만으로 만든 직접 주소가 깨진다.
- 링크는 사용자가 누르는 주소일 뿐 스크립트는 Booking·Google 에 요청하지 않는다. `--name` 이 없으면 가격만 나온다.

### 가격 달력 (heatmap)

체크아웃 기준 한 달치 날짜를 싼 날/평균/비싼 날로 나눠, 하루 이틀 옮겨 싸게 잡을 수 있게 한다.

### 지역 + 예산으로 찾기

이 스킬은 **특정 호텔**의 가격만 조회한다. "장충동에서 8만~13만원 호텔 찾아줘" 같은 질의는 이 순서로 한다(항상):

1. **발견** — `WebSearch` 로 그 지역 호텔 후보와 TripAdvisor URL 을 찾는다("장충동 호텔 tripadvisor").
2. **후보 제시 → 선택 대기** — 후보를 목록(이름·위치·대략 등급)으로 보여 주고 **어느 호텔을 볼지 사용자의 선택을 기다린다.**
   임의로 골라 진행하지 않는다. 사용자가 "다 비교해줘" 라고 하면 후보 전부를 조회한다.
3. **가격** — 고른 호텔마다 `rates` 를 한 번씩 실행한다. **"N곳이면 요청 N회(+환율 1회)"** 를 먼저 알린다.
4. **필터** — 예산 대역(원화)에 드는 것만 표로 보여 준다. 맞는 호텔이 없으면 "못 찾음" 으로 말한다.

사용자가 특정 호텔을 콕 집으면 2번을 건너뛰고 바로 조회한다.

### 실패 표

실패하면 stderr 에 `오류: …` 한 줄(`--format json` 이면 stdout 에 `{"status":"error","error":<종류>,"detail":…}` 도)과 종료 코드.

| `error` | 뜻 | 대응 |
|---|---|---|
| `network_error`·`timeout` | 연결 실패·시간 초과(한 번 더 받은 뒤) | 잠시 뒤 같은 명령을 다시 실행한다. 반복되면 사용자에게 알린다 |
| `http` | Xotelo 5xx·408·429 또는 JSON 아닌 오류 본문(한 번 더 받은 뒤) | 잠시 뒤 다시 실행한다 |
| `site` | JSON 이 아니거나 `rates`·`heatmap` 이 없다 | 점검 중이거나 구조 변경 — 다시 실행해도 같으면 사용자에게 알린다 |
| `mismatch` | 응답이 되비친 날짜·통화가 요청과 다르다 | 다시 실행한다. 반복되면 사용자에게 알린다 |
| `args`(Xotelo 400 포함) | 인자 오류 | `detail` 을 그대로 전한다(통화·날짜 확인) |
| `api` | Xotelo 가 400 밖의 오류 객체를 줬다 | `detail` 을 그대로 전한다 |
| `no_result` | 그 날짜에 요금이 0건 | 매진·미등재 호텔·날짜를 확인하라고 전한다 |
| 환율 실패 | 원화 환산만 빠진다(실패 아님) | `warnings`·주석의 "원화 환산 생략 — 사유" 를 그대로 전한다 |

## 명령 레퍼런스

`rates`·`heatmap` 공통: `--hotel-key g#-d#` **또는** `--url <TripAdvisor URL>`(택1, 필수) · `--name <표시명>`(선택) ·
`--format {markdown,json}`(기본 markdown) · `--output <경로>`.

| 인자 | 대상 | 설명 |
|------|:---:|------|
| `--checkin` | rates | 체크인 `YYYY-MM-DD` |
| `--checkout` | 둘 다 | 체크아웃 `YYYY-MM-DD`(rates 는 체크인보다 이후) |
| `--currency` | rates | Xotelo 수집 통화(기본 USD — KRW 미지원, 원화는 환산 표시) |
| `--adults` / `--rooms` | rates | 성인 수(기본 2) / 객실 수(기본 1) |
| `--no-krw` | rates | 원화 환산 생략(환율을 받지 않는다) |
| `--cache-dir` / `--no-cache` | rates | 환율 캐시 폴더(기본 `~/.cache/itda-cc/hotel-search`) / 캐시 안 씀 |

지원 수집 통화: USD·GBP·EUR·CAD·CHF·AUD·JPY·CNY·INR·THB·BRL·HKD·RUB·BZD(KRW 없음). 엔드포인트·응답 상세는 [references/sources.md](references/sources.md).

| 종료 코드 | 의미 |
|------|------|
| 0 | 성공 |
| 1 | 네트워크·응답 판독·저장 실패 |
| 2 | 인자 오류(필수 누락, 날짜 형식/역순, hotel_key 미해소, KRW 등 미지원 통화, Xotelo 400) |
| 3 | 결과 없음(해당 날짜 요금 0건 — 매진·미커버 호텔) |

## 제한 사항

- **트립어드바이저 메타값** — 실제 예약가와 다를 수 있다. 예약 전 해당 사이트에서 다시 확인하라고 늘 말한다.
- **사이트별 대표가 1개** — 객실 타입별 가격은 없다. 세금(`tax`)도 대부분 비어 있다.
- **사이트 노출 개수 편차** — 호텔·날짜에 따라 1~4곳만 뜰 수 있다.
- **이름 검색 없음** — TripAdvisor 등재 호텔만 조회된다.
- **조회 전용·비공식 표면** — 공식 파트너 API 가 아니다. 개인 참고 목적으로만 쓴다.
