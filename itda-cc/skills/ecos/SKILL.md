---
name: ecos
description: >
  한국은행 ECOS API로 거시경제 지표를 Claude Code 에서 직접 조회하는 스킬입니다.
  "GDP 추이 알려줘", "금리 환율 정리해줘", "100대 경제지표 확인해줘", "소비자물가지수 2020~2024 연간"처럼 말하면 됩니다.
  GDP·금리·환율·CPI·100대 핵심 지표·통계용어를 다루며 키는 .env 의 ECOS_API_KEY 에서 읽습니다.
  [책임 경계] 본 스킬은 Claude Code 에서 ECOS 직접 조회 전담 — itda-gov:ecos 는 Cowork·itda-hyve 경로.
license: Apache-2.0
compatibility: "Claude Code 전용. Python 3.10+(표준 라이브러리만). 스크립트가 ecos.bok.or.kr 에 직접 요청하고, 키는 .env 의 ECOS_API_KEY 에서 읽는다."
allowed-tools: "Bash, Read, Write"
user-invocable: true
argument-hint: "[key|search|word|items|tables] 지표·통계표코드·기간 (예: 소비자물가지수 2020~2024 연간)"
metadata:
  author: "스킬.잇다 <dev@itda.work>"
  category: "domain"
  status: "active"
  version: "0.1.0"
  created_at: "2026-11-02"
  updated_at: "2026-11-02"
  tags: "GDP, ECOS, CPI, economics, interest rate, exchange rate, Bank of Korea"
---

# ecos

한국은행 ECOS(경제통계시스템) API로 거시경제 지표를 수집합니다.
GDP·금리·환율·물가·100대 경제지표 등 정책 보고서와 사업계획서에 필요한 경제 데이터를 제공합니다.

- **5개 서비스**: 100대 지표(key) · 통계 조회(search) · 세부항목(items) · 통계표 목록(tables) · 용어사전(word)
- **명령 한 번에 결과**: 스크립트가 ECOS 에 직접 요청하고, 응답의 `list_total_count` 까지 1000행씩 이어 받아 전량 대조한다 — 모자라면 실패로 끝낸다

## 키 — `.env` 하나에서만 읽는다

스크립트는 `ECOS_API_KEY` 를 **`.env` 파일 하나**에서 읽는다. 찾는 순서는 `--env-file <경로>` → 현재 폴더 `./.env` → 홈 `~/.env` 이고,
**처음 찾은 파일 하나만** 쓴다(현재 폴더 `.env` 에 키가 없으면 `~/.env` 로 넘어가지 않고 `env_key_missing` 으로 멈춘다).
프로세스 환경변수는 보지 않는다. 출력 JSON 의 `env_file` 이 실제로 읽은 파일이다.

```
ECOS_API_KEY=발급받은키
```

- **`.env` 를 Read·cat 으로 열지 않는다.** 키가 있는지는 스크립트를 돌려 `env_key_missing`·`env_file_missing` 으로 안다.
- **키 값을 대화에 출력하지 않는다.** 키는 URL 경로에 들어가지만, 출력·오류의 URL 에는 `***` 로 가려 싣는다.
- 사용자가 대화에 키를 붙여 넣으면 **그 값을 쓰지 않는다** — `.env` 에 `ECOS_API_KEY=…` 로 적으라고 안내한다(발급·형식은 GUIDE.md).
- `env_key_missing`·`env_file_missing` 이면 멈추고, 출력의 `env_file`(어느 파일을 봤는지)과 함께 `.env` 에 키를 넣으라고 알린다.
  `.env` 권한이 넓으면 stderr 에 경고가 나온다 — `chmod 600 .env` 를 권한다.

발급: <https://ecos.bok.or.kr/api/> 회원가입 → 인증키 신청(즉시 발급).

## 준비

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
printf "%s\n" "$c"' _ ecos itda-cc "${SKILL_DIR:-}" "${CLAUDE_PLUGIN_ROOT:-}" "${CLAUDE_CONFIG_DIR:-}")
: "${SKILL_DIR:?정하지 못했다 — 스킬을 불러올 때 받은 base directory(이 SKILL.md 가 있는 절대경로)를 SKILL_DIR 에 넣고 이 블록을 다시 실행하라}"
```

**Python 명령** — 이 문서의 예시는 macOS/Linux 기준 `python3` 로 적었다. **Windows**(PowerShell·Git Bash 모두)에서는 `python3` 대신 `py -3` 로 실행하고, `py` 가 없으면 `python` 을 쓴다. Windows 의 `python3` 는 대개 Microsoft Store 별칭이라 실행되지 않는다(exit 49). 어느 명령이든 Python 3.10 이상이어야 한다.

설치할 의존성은 없다(표준 라이브러리만).

## 명령

모든 명령은 `--format json|table`·`--env-file PATH`·`--max-calls N` 을 받는다(서브커맨드 앞·뒤 어디든).

```bash
C="$SKILL_DIR/scripts/collect_econ.py"

python3 "$C" key                                                            # 100대 주요 경제지표
python3 "$C" search --stat 901Y009 --period year --start 2020 --end 2024    # 소비자물가지수 연간
python3 "$C" search --stat 200Y106 --period quarter --start 2020Q1 --end 2024Q4   # 분기 GDP
python3 "$C" search --stat 731Y003 --period day --start 20240102 --end 20240131 --item1 0000003   # 원/달러 종가
python3 "$C" items --stat 901Y009                                           # 통계표의 항목코드
python3 "$C" tables                                                         # 통계표 목록
python3 "$C" word --word 기준금리                                            # 용어 정의
python3 "$C" --format table key
```

- **`--period`**: `year`(A) · `semi`(S) · `quarter`(Q) · `month`(M) · `day`(D) — 이름이나 코드 어느 쪽이든. `--start`·`--end` 는 주기 형식을 따른다 —
  `2024` · `2024S1` · `2024Q1` · `202401` · `20240101`. 형식이 어긋나면 `ERROR-101` 이다.
- **항목코드**는 필요할 때만 `--item1`(·`--item2`)로 붙인다. 코드를 모르면 `items` 를 먼저 돌린다. `--item1` 없이 `--item2` 는 거부한다.
- **통계표코드를 모르면** `tables`(전체 목록)나 [references/ecos.md](references/ecos.md) 의 자주 쓰는 코드 표를 본다.
- **`word`** 의 한글 용어는 그대로 준다 — 스크립트가 경로에 맞게 인코딩한다.

### 쪽 이어받기 — 1000행씩, `list_total_count` 까지

한 요청은 1000행씩이다. 스크립트가 1쪽을 받아 `list_total_count` 를 보고 남은 쪽을 받은 뒤 전량 대조한다
(2026-09-30 실측: 100대 지표 101 · 통계표 목록 844 · 901Y009 세부항목 **1,743** — 세부항목은 2쪽이다).

- **남은 호출이 `--max-calls`(기본 5 = 5,000행 초과)를 넘으면 받지 않고** `error: "confirm_first"` + `need_calls`·`total_count` 로 멈춘다.
  사용자에게 호출 수를 알리고 확인받는다 — 기간을 줄이거나 항목코드를 붙이는 쪽을 먼저 권한다(일간 표를 항목코드 없이 장기로 받으면
  수십만 행이 될 수 있다). 사용자가 다 받자고 하면 `--max-calls <need_calls>` 를 붙여 다시 실행한다.
- 전량 대조(모든 쪽의 `list_total_count` 가 같은가 · 행 범위가 겹치지 않는가 · 같은 행이 두 번 나오지 않는가 · 1행부터 빈틈없는가)가
  어긋나면 전 쪽을 한 번 더 받는다. 그래도 어긋나면 `error: "incomplete"`(빈 범위 `missing_ranges`) 또는 `error: "response"` 로 멈춘다 —
  **incomplete 인 채로 결과를 말하지 않는다.**

### 다시 받기·오류 — 스크립트가 판정한다

ECOS 는 오류도 HTTP 200 으로 준다. 본문이 `{"RESULT": {"CODE": …}}` 면 오류다(`INFO-200` 데이터 없음만 빈 결과로 성공). 판정은 스크립트가 한다.

- 연결 오류·시간 초과·HTTP 5xx·429·JSON 이 아닌 본문·`ERROR-500`·`ERROR-600`·`ERROR-601` 은 2초 쉬고 **한 번 더** 받는다(stderr `[참고]` 줄).
- `ERROR-602`(과도한 호출)는 **다시 부르지 않고 멈춘다** — 잠시 뒤에 다시. `ERROR-400`(범위 초과)은 기간을 줄여 다시.
- `INFO-100`(인증키 무효)이면 멈추고 `.env` 의 키(앞뒤 공백·발급 직후 미반영)를 확인하라고 알린다.
- 여러 지표·여러 통계표를 한 번에 요청받으면 **예상 호출 수를 먼저 알린다**(명령마다 보통 1회, 1000행마다 1회 더).

## 출력

json: `status`·`count`·`total_count`(`list_total_count`)·`items`(search 는 `data`)·`sources`(쪽마다 가린 요청 URL `request`·`start_row`·`total_count`·`rows`)·`env_file`.
`search` 는 `stat_code`·`period`(TIME 형식으로 추정)와, 값이 숫자가 아니라 뺀 행 수 `skipped_non_numeric`(0 이 아니면 `warnings`)를 싣는다.
응답에 `list_total_count` 가 없으면 받은 행 수로 세되 `warnings` 에 "전량 기준선이 없다" 를 싣는다 — 전량이라고 말하지 않는다.

## 종료 코드

| 코드 | 의미 |
|------|------|
| 0 | 성공 (`INFO-200` 데이터 없음은 `count: 0` 성공) |
| 1 | 실패 — `error`: `env_file_missing`·`env_key_missing`·`env_file_unreadable`(`.env`) · `api`(본문 RESULT.CODE, `error_code`) · `network`·`http`·`response`(다시 받아도 같음·전량 대조 어긋남) · `incomplete`(행 범위가 빔, `missing_ranges`) · `confirm_first`(호출 상한 초과 — 받지 않음, `need_calls`) |
| 2 | 인자 오류 (`args`) |

## 오류 코드 (ECOS API 6개 공통)

| 코드 | 의미 | 조치 |
|------|------|------|
| INFO-100 | 인증키 무효 | `.env` 의 `ECOS_API_KEY` 확인(앞뒤 공백), 발급 직후면 수 분 뒤 |
| INFO-200 | 데이터 없음 | 정상 응답(결과 0건) — `items` 로 항목·기간(`START_TIME`~`END_TIME`) 확인 |
| ERROR-100 | 필수 값 누락 | 인자 확인 |
| ERROR-101 | 주기/날짜 형식 불일치 | A:2024 / S:2024S1 / Q:2024Q1 / M:202401 / D:20240101 |
| ERROR-200 · 300 · 301 | 파일타입·조회건수 오류 | 스크립트가 정한다 — 나오면 문의 |
| ERROR-400 | 검색범위 초과 (60초 TIMEOUT) | 기간을 좁혀 다시 |
| ERROR-500 · 600 · 601 | 서버·DB·SQL 오류 | 스크립트가 한 번 더 받는다 — 그래도 같으면 나중에 |
| ERROR-602 | 과도한 호출로 이용 제한 | 다시 부르지 않는다 — 잠시 뒤에 |

## 응답 규칙 (모델 표현)

- JSON 원문을 붙여넣지 말고 핵심 수치·시점·단위를 요약한다. 단위(`unit`)를 빼먹지 않는다.
- `warnings` 가 있으면 그대로 알린다. 답변 말미에 `※ 한국은행 ECOS 통계 기준` 을 한 줄 남긴다.

## 이 스킬을 쓰지 않을 때

| 상황 | 대신 쓸 스킬 |
|---|---|
| Cowork 에서 경제통계를 조회할 때 | `itda-gov:ecos` |
| 개별 기업의 재무·공시 | `itda-cc:dart` |

## 파일 구조

```
ecos/
  SKILL.md · GUIDE.md · CHANGELOG.md
  scripts/
    ecos_api.py       # 직접 요청·다시 받기·응답 판정·전량 대조·오류 코드 분류
    collect_econ.py   # CLI (key/search/items/tables/word)
  tests/              # urlopen 을 바꿔 끼운 단위 테스트(네트워크 없음) + fixtures/(2026-09-30 실측 응답, 공개 시험 키 sample)
  references/
    ecos.md           # 요청 URL·주기 형식·자주 쓰는 통계표코드
    ecos-매뉴얼/       # 한국은행 정본 명세 (xls + 발췌 md 6종)
```

`.env` 판독(`cc_env.py`)과 HTTP(`cc_http.py`)는 플러그인 `shared/` 에 있고 배포 때 `scripts/` 로 들어간다.
